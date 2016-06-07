import os, time

from requests import session, RequestException, Timeout
from urllib.parse import urlencode
from os import path

from .parsers import *
from .database import SyncMode
from .util import prompt_choice, ellipsize


class SessionError(Exception):
    pass

class LoginError(SessionError):
    pass


def raise_fetch_error(page, e):
    raise SessionError("Unable to fetch {}: {}".format(page, str(e)))


class Session:
    def sso_url(self, url):
        return self.server_config["sso_base"] + url

    def studip_url(self, url):
        return self.server_config["studip_base"] + url


    def __init__(self, config, db, user_name, password, sync_dir):
        self.db = db
        self.server_config = config["server"]
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
            semester = parse_selected_semester(self.overview_page)
        except ParserError:
            raise SessionError("Unable to parse overview page")

        if semester != "current":
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
            sync = prompt_choice("Synchronize \"{}\"? ([Y]es, [n]o, [m]etadata only)".format(
                    ellipsize(course.name, 50)), "ynm", default="y")
            course.sync = { "y" : SyncMode.Full, "n" : SyncMode.NoSync, "m" : SyncMode.Metadata }[
                    sync]
            self.db.add_course(course)

        sync_courses = self.db.list_courses(full=True, select_sync_no=False)
        last_course_synced = False
        db_files = self.db.list_files()
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
            print(" new files for " + course.name)

            for i, file_id in enumerate(new_files):
                print("Fetching metadata for file {}/{}...".format(i+1, len(new_files)),
                        end="", flush=True)

                open_url = folder_url + "&open=" + file_id
                try:
                    r = self.http.get(open_url)
                except RequestException as e:
                    raise_fetch_error("overview page", e)

                try:
                    file = parse_file_details(course.id, r.text)
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

        try:
            for file in self.db.list_files(full=True, select_sync_metadata_only=False,
                    select_sync_no=False):

                # Replace regular '/' by 'DIVISION SLASH' (U+2215) to create a valid directory name
                def unslash(str):
                    return str.replace("/", "\u2215")

                tokens = {
                    "course-id": file.course,
                    "course": unslash(file.course_name),
                    "path": path.join(*map(unslash, file.path)),
                    "id": file.id,
                    "name": file.name,
                    "ext": file.extension,
                    "description": file.description,
                    "author": file.author,
                    "time": file.created
                }

                path_format = "{course}/{path}/{name}.{ext}"
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
