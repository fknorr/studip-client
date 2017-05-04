import os, time, threading, ctypes

from requests import session, RequestException, Timeout
from urllib.parse import urlencode
from os import path
from threading import Thread, Condition, Lock
from copy import deepcopy
from enum import IntEnum

from .parsers import *
from .database import SyncMode
from .util import prompt_choice, ellipsize, escape_file_name
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
            r = self.http.get(self.studip_url("/studip/index.php?again=yes&sso=shib"))
        except RequestException as e:
            raise_fetch_error("login page", e)

        try:
            form_data = parse_login_form(r.text)
        except ParserError:
            raise LoginError("Error parsing login page")

        try:
            r = self.http.post(
                    self.sso_url(form_data.post_url),
                    data = {
                        "j_username": user_name,
                        "j_password": password,
                        "uApprove.consent-revocation": "",
                        "_eventId_proceed": ""
                    }
                )
        except RequestException as e:
            raise_fetch_error("login confirmation page", e)

        try:
            form_data = parse_saml_form(r.text)
        except ParserError as e:
            message = "Login failed"
            if e.message:
                message += ": " + e.message
            raise LoginError(message)

        try:
            r = self.http.post(self.studip_url("/Shibboleth.sso/SAML2/POST"), form_data)
        except RequestException as e:
            raise_fetch_error("login page", e)


    def update_metadata(self):
        url = self.studip_url("/studip/dispatch.php/my_courses/set_semester")
        try:
            overview_page = self.http.post(url, data={ "sem_select": "current" }).text
        except RequestException as e:
            raise_fetch_error("overview page", e)

        try:
            semester_list = parse_semester_list(overview_page)
        except ParserError:
            raise SessionError("Unable to parse overview page")

        self.db.update_semester_list(semester_list.semesters)

        try:
            remote_courses = parse_course_list(overview_page)
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
        db_files = self.db.list_files(full=True, select_sync_yes=True,
                select_sync_metadata_only=True, select_sync_no=False)
        db_file_dict = dict((f.id, f) for f in db_files)

        concurrency = int(self.config["connection", "update_concurrency"])
        with SessionPool(concurrency, self.http.cookies) as pool:
            for course in sync_courses:
                course_url = self.studip_url("/studip/seminar_main.php?auswahl=" + course.id)
                folder_url = self.studip_url("/studip/folder.php?cid=" + course.id + "&cmd=all")

                try:
                    self.http.get(course_url, timeout=(None, 0.001))
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

                new_files = [ file_id for file_id, _ in file_list if file_id not in db_file_dict ]
                updated_files = [ file_id for file_id, date in file_list
                        if file_id  in db_file_dict and db_file_dict[file_id].remote_date != date ]

                if len(new_files) > 0:
                    new_files_str = ("" if last_course_synced else "\n") + str(len(new_files))
                    last_course_synced = True
                else:
                    new_files_str = "No"
                    last_course_synced = False

                updated_files_str = ""
                if len(updated_files) > 0:
                    updated_files_str = ", {} updated ".format(len(updated_files))

                print("{} new{} file(s) for {} {} ".format(new_files_str, updated_files_str,
                        course.type, course.name))

                files_to_fetch = new_files + updated_files
                for file_id in files_to_fetch:
                    pool.defer_request("GET", folder_url + "&open=" + file_id)
                pool.done()

                for i, request in enumerate(pool):
                    try:
                        file = parse_file_details(course.id, request.text)
                    except ParserError:
                        raise SessionError("Unable to parse file details")

                    print("Fetched metadata for file {}/{}: ".format(i+1, len(files_to_fetch)),
                            end="", flush=True)
                    if file.complete():
                        if file.id in new_files:
                            self.db.add_file(file)
                        else:
                            self.db.update_file(file)
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
            date_mismatch = not file.local_date or file.local_date != file.remote_date

            if date_mismatch or not path.isfile(file_path):
                if path.isfile(file_path) and date_mismatch:
                    base_path = file_path
                    v = 1
                    file_path = "{}.{}".format(base_path, v)
                    while path.isfile(file_path):
                        v += 1
                        file_path = "{}.{}".format(base_path, v)

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

                file.local_date = file.remote_date

                timestamp = time.mktime(file.local_date.timetuple())
                os.utime(file_path, (timestamp, timestamp))

                self.db.update_file_local_date(file)
                self.db.commit()

