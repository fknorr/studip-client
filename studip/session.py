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
from .async import ThreadPool


class SessionError(Exception):
    pass

class LoginError(SessionError):
    pass


def raise_fetch_error(page, e):
    raise SessionError("Unable to fetch {}: {}".format(page, str(e)))


class SessionPool(ThreadPool):
    def __init__(self, n_threads, cookies):
        super().__init__(n_threads, { "cookies": cookies })

    def init_thread(self, local_state):
        session = requests.session()
        session.cookies = local_state["cookies"]
        local_state["session"] = session

    def cleanup_thread(self, local_state):
        local_state["session"].close()

    def execute_task(self, local_state, task):
        return local_state["session"].request(task["method"], *task["args"], **task["kwargs"])

    def defer_request(self, method, *args, **kwargs):
        self.defer({ "method": method, "args": args, "kwargs": kwargs })


class Session:
    def sso_url(self, url):
        return self.config["server", "sso_base"] + url

    def studip_url(self, url):
        return self.config["server", "studip_base"] + url


    def __init__(self, config, db, user_name, password, sync_dir):
        self.db = db
        self.config = config
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

        concurrency = int(self.config["connection", "update_concurrency"])
        with SessionPool(concurrency, self.http.cookies) as pool:
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
                    pool.defer_request("GET", folder_url + "&open=" + file_id)
                pool.done()

                for i, request in enumerate(pool):
                    try:
                        file = parse_file_details(course.id, request.text)
                    except ParserError:
                        raise SessionError("Unable to parse file details")

                    print("Fetched metadata for file {}/{}: ".format(i+1, len(new_files)),
                            end="", flush=True)
                    if file.complete():
                        self.db.add_file(file)
                        print(" " + file.description)
                    else:
                        print(" <bad format>")


    def fetch_files(self):
        first_file = True
        files_dir = path.join(self.sync_dir, ".studip", "files")
        os.makedirs(files_dir, exist_ok=True)

        pending_files = self.db.list_files(full=True, select_sync_metadata_only=False,
                select_sync_no=False)

        for i, file in enumerate(pending_files):
            file_path = path.join(files_dir, file.id)
            if not path.isfile(file_path):
                if first_file:
                    print()
                    first_file = False
                print("Fetching file {}/{}: {}...".format(i+1, len(pending_files),
                        ellipsize(file.description, 50)))

                url = self.studip_url("/studip/sendfile.php?force_download=1&type=0&" \
                        + urlencode({"file_id": file.id, "file_name": file.name }))
                try:
                    r = self.http.get(url)
                except RequestException as e:
                    raise SessionError("Unable to download file {}: {}".format(file.name, e))

                with open(file_path, "wb") as writer:
                    writer.write(r.content)
                    timestamp = time.mktime(file.created.timetuple())

                os.utime(file_path, (timestamp, timestamp))
