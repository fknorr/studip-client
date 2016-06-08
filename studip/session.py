import os, time, threading, ctypes

from requests import session, RequestException, Timeout
from urllib.parse import urlencode
from os import path
from threading import Thread, Condition, Lock
from copy import deepcopy
from enum import IntEnum

from .parsers import *
from .database import SyncMode
from .util import prompt_choice, ellipsize


class SessionError(Exception):
    pass

class LoginError(SessionError):
    pass


def raise_fetch_error(page, e):
    raise SessionError("Unable to fetch {}: {}".format(page, str(e)))


class ExitThread(BaseException):
    pass


class SessionPool:
    def __init__(self, n_threads, cookies):
        self.threads = [ Thread(target=lambda: self.thread_main(deepcopy(cookies)))
                for _ in range(n_threads) ]

        self.queue = []
        self.results = []
        self.last_req_no = -1
        self.last_finished_no = -1
        self.done_at_no = -1
        self.lock = Lock()
        self.thread_cv = Condition(self.lock)
        self.iter_cv = Condition(self.lock)

        for thread in self.threads:
            thread.start()

    def thread_main(self, cookies):
        session = requests.session()
        try:
            session.cookies = cookies
            while True:
                with self.lock:
                    self.thread_cv.wait_for(lambda: self.queue)
                    id, no, args, kwargs = self.queue.pop(0)
                result = (id, session.request(*args, **kwargs))
                with self.lock:
                    self.results.append(result)
                    self.last_finished_no += 1
                    self.iter_cv.notify()
        except ExitThread:
            pass
        finally:
            session.close()

    def request(self, id, *args, **kwargs):
        with self.lock:
            self.done_at_no = -1
            self.last_req_no += 1
            self.queue.append((id, self.last_req_no, args, kwargs))
            self.thread_cv.notify()

    def __iter__(self):
        with self.lock:
            while self.last_finished_no <= self.done_at_no:
                self.iter_cv.wait_for(
                        lambda: self.last_finished_no >= self.done_at_no or self.results)
                if self.results:
                    yield self.results.pop(0)
                else:
                    break
        raise StopIteration()

    def done(self):
        with self.lock:
            self.done_at_no = self.last_req_no

    def close(self):
        for thread in self.threads:
            # raise ExitThread in every thread
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident),
                ctypes.py_object(ExitThread))
        with self.lock:
            # Wake up all waiting threads to handle exception
            self.thread_cv.notify_all()
        for thread in self.threads:
            thread.join()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class Session:
    def sso_url(self, url):
        return self.server_config["sso_base"] + url

    def studip_url(self, url):
        return self.server_config["studip_base"] + url


    def __init__(self, config, db, user_name, password, sync_dir):
        self.db = db
        self.server_config = config["server"]
        self.fs_config = config["filesystem"]
        self.sync_dir = sync_dir

        self.http = requests.session()

        try:
            self.http.get(self.studip_url("/studip/index.php?again=yes&sso=shib"))
        except RequestException as e:
            raise_fetch_error("login page", e)

        try:
            r = self.http.post(self.sso_url("/idp/Authn/UserPassword"), data = {
                "j_username": user_name,
                "j_password": password,
                "uApprove.consent-revocation": ""
            })
        except RequestException as e:
            raise_fetch_error("login confirmation page", e)

        try:
            form_data = parse_saml_form(r.text)
        except ParserError:
            raise LoginError("Login failed")

        try:
            r = self.http.post(self.studip_url("/Shibboleth.sso/SAML2/POST"), form_data)
        except RequestException as e:
            raise_fetch_error("login page", e)

        self.overview_page = r.text


    def update_metadata(self):
        try:
            semester_list = parse_semester_list(self.overview_page)
        except ParserError:
            raise SessionError("Unable to parse overview page")

        self.db.update_semester_list(semester_list.semesters)

        if semester_list.selected != "current":
            url = self.studip_url("/studip/dispatch.php/my_courses/set_semester")
            try:
                self.overview_page = self.http.post(url, data={ "sem_select": "current" }).text
            except RequestException as e:
                raise_fetch_error("overview page", e)

        try:
            remote_courses = parse_course_list(self.overview_page)
        except ParserError:
            raise SessionError("Unable to parse course list")

        remote_course_ids = [course.id for course in remote_courses]

        db_course_ids = self.db.list_courses()
        new_courses = (course for course in remote_courses if course.id not in db_course_ids)
        removed_course_ids = (id for id in db_course_ids if id not in remote_course_ids)

        for course_id in removed_course_ids:
            course = self.db.get_course_details(course_id)
            choice = prompt_choice("Delete data for removed course \"{}\"? ([Y]es, [n]o)".format(
                    ellipsize(course.name, 50)), "yn", default="y")
            if choice == "y":
                self.db.delete_course(course)

        for course in new_courses:
            sync = prompt_choice("Synchronize {} {}? ([Y]es, [n]o, [m]etadata only)".format(
                    course.type, ellipsize(course.name, 40)), "ynm", default="y")
            course.sync = { "y" : SyncMode.Full, "n" : SyncMode.NoSync, "m" : SyncMode.Metadata }[
                    sync]
            self.db.add_course(course)

        sync_courses = self.db.list_courses(full=True, select_sync_no=False)
        last_course_synced = False
        db_files = self.db.list_files()

        with SessionPool(4, self.http.cookies) as pool:
            for course in sync_courses:
                course_url = self.studip_url("/studip/seminar_main.php?auswahl=" + course.id)
                folder_url = self.studip_url("/studip/folder.php?cid=" + course.id + "&cmd=all")

                try:
                    self.http.get(course_url, timeout=(None, 0))
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Timeout:
                    pass
                except RequestException as e:
                    raise SessionError("Unable to set course: {}".format(str(e)))

                r = self.http.get(folder_url)
                try:
                    file_list = parse_file_list(r.text)
                except ParserError:
                    raise SessionError("Unable to parse file list")

                if last_course_synced:
                    print()

                new_files = [ file_id for file_id in file_list if file_id not in db_files ]
                if len(new_files) > 0 :
                    if not last_course_synced:
                        print()
                    print(len(new_files), end="")
                    last_course_synced = True
                else:
                    print("No", end="")
                    last_course_synced = False
                print(" new files for {} {} ".format(course.type, course.name))

                for file_id in new_files:
                    pool.request(file_id, "GET", folder_url + "&open=" + file_id)
                pool.done()

                for i, (file_id, request) in enumerate(pool):
                    print("Parsing metadata for file {}/{}...".format(i+1, len(new_files)),
                            end="", flush=True)

                    try:
                        file = parse_file_details(course.id, request.text)
                    except ParserError:
                        raise SessionError("Unable to parse file details")

                    if file.complete():
                        self.db.add_file(file)
                        print(" " + file.description)
                    else:
                        print(" <bad format>")


    def download_files(self):
        first_file = True
        modified_folders = set()
        copyrighted_files = []

        path_format = self.fs_config["path_format"]

        try:
            for file in self.db.list_files(full=True, select_sync_metadata_only=False,
                    select_sync_no=False):

                # Replace regular '/' by 'DIVISION SLASH' (U+2215) to create a valid directory name
                def unslash(str):
                    return str.replace("/", "\u2215")

                def make_path(folders):
                    return path.join(*map(unslash, folders)) if folders else ""

                descr_no_ext = file.description
                if descr_no_ext.endswith("." + file.extension):
                    descr_no_ext = descr_no_ext[:-1-len(file.extension)]

                short_path = file.path
                if short_path[0] == "Allgemeiner Dateiordner":
                    short_path = short_path[1:]

                tokens = {
                    "semester": file.course_semester,
                    "course-id": file.course,
                    "course": unslash(file.course_name),
                    "type": unslash(file.course_type),
                    "path": make_path(file.path),
                    "short-path": make_path(short_path),
                    "id": file.id,
                    "name": file.name,
                    "ext": file.extension,
                    "description": file.description,
                    "descr-no-ext": descr_no_ext,
                    "author": file.author,
                    "time": file.created
                }

                try:
                    rel_path = path_format.format(**tokens)
                except Exception:
                    raise SessionError("Invalid path format: " + path_format)

                # First update modified_folders, then create directories.
                folder = path.dirname(rel_path)
                while folder:
                    modified_folders.add(folder)
                    folder = path.dirname(folder)

                abs_path = path.join(self.sync_dir, rel_path)
                os.makedirs(path.dirname(abs_path), exist_ok=True)

                if not path.isfile(abs_path):
                    if first_file:
                        print()
                        first_file = False
                    print("Downloading file {}...".format(rel_path))

                    url = self.studip_url("/studip/sendfile.php?force_download=1&type=0&" \
                            + urlencode({"file_id": file.id, "file_name": file.name }))
                    try:
                        r = self.http.get(url)
                    except RequestException as e:
                        raise SessionError("Unable to download file {}: {}".format(file.name, e))

                    with open(abs_path, "wb") as writer:
                        writer.write(r.content)
                        timestamp = time.mktime(file.created.timetuple())

                    if file.copyrighted:
                        copyrighted_files.append(rel_path)

                    os.utime(abs_path, (timestamp, timestamp))

        finally:
            modified_folders = list(modified_folders)
            modified_folders.sort(key=lambda f: len(f), reverse=True)

            def update_directory_mtime(dir):
                latest_ctime = 0
                for file in os.listdir(dir):
                    if not file.startswith("."):
                        latest_ctime = max(latest_ctime, path.getmtime(dir + "/" + file))

                # This may fail if a directory has not been created yet.
                try:
                    os.utime(dir, (latest_ctime, latest_ctime))
                except Exception:
                    pass

            for folder in modified_folders:
                update_directory_mtime(path.join(self.sync_dir, folder))
            update_directory_mtime(self.sync_dir)

            if copyrighted_files:
                print("\n" + "-"*80)
                print("The following files have special copyright notices:\n")
                for file in copyrighted_files:
                    print("  -", file)
                print("\nPlease make sure you have looked up, read and understood the terms and"
                        " conditions of these files before proceeding to use them.")
                print("-"*80 + "\n")
