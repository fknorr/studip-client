import requests
import os

from parsers import *
from database import Database
from util import prompt_choice, ellipsize


class Session:
    def __init__(self, config, db, user_name, password, sync_dir):
        self.db = db
        self.config = config
        self.sync_dir = sync_dir

        self.http = requests.session()
        self.http.get(config["studip_base"] + "/studip/index.php?again=yes&sso=shib")

        r = self.http.post(config["sso_base"] + "/idp/Authn/UserPassword", data = {
            "j_username": user_name,
            "j_password": password,
            "uApprove.consent-revocation": ""
        })

        form_data = parse_saml_form(r.text)
        r = self.http.post(config["studip_base"] + "/Shibboleth.sso/SAML2/POST", form_data)
        self.overview_page = r.text


    def update_metadata(self):
        remote_courses = parse_course_list(self.overview_page)

        db_courses = self.db.list_courses()
        print([c for c in db_courses])
        new_courses = (course for course in remote_courses if course not in db_courses)
        removed_courses = (course for course in db_courses if course not in remote_courses)

        for course in removed_courses:
            choice = prompt_choice("Delete data for removed course \"{}\"? ([Y]es, [n]o)".format(
                    ellipsize(course["name"], 50)), "yn", default="y")
            if choice == "y":
                self.db.delete_course(course)

        for course_id in new_courses:
            course = remote_courses[course_id]
            sync = prompt_choice("Synchronize \"{}\"? ([Y]es, [n]o, [m]etadata only)".format(
                    ellipsize(course["name"], 50)), "ynm", default="y")
            course["sync"] = { "y" : "yes", "n" : "no", "m" : "metadata only" }[sync]
            self.db.add_course(course_id, course)

        sync_courses = self.db.list_courses(full=True, select_sync_no=False)
        last_course_synced = False
        db_files = self.db.list_files()
        for course in sync_courses:
            base_url = self.config["studip_base"] + "/studip"
            course_url = base_url + "/seminar_main.php?auswahl=" + course.id
            folder_url = base_url + "/folder.php?cid=" + course.id + "&cmd=all"

            try:
                self.http.get(course_url, timeout=(None, 0))
            except (KeyboardInterrupt, SystemExit):
                raise
            except requests.Timeout:
                pass

            r = self.http.get(folder_url)
            file_list = parse_file_list(r.text)

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
                r = self.http.get(open_url)
                details = parse_file_details(r.text)
                if all(attr in details for attr in ["name", "url", "folder"]):
                    file = database.File(file_id, details["name"], date.today())
                    self.db.add_file(file)
                    print(" " + details["description"])
                else:
                    print(" <bad format>")


    def download_files(self):
        first_file = True
        for file in self.db.list_files(full=True, sync_courses_only=True):
            dir_path = self.sync_dir + "/" + file["path"]
            os.makedirs(dir_path, exist_ok=True)
            rel_path = file["path"] + "/" + file["name"]
            abs_path = dir_path + "/" + file["name"]
            if not os.path.isfile(abs_path):
                if first_file:
                    print()
                    first_file = False
                print("Downloading file {}...".format(rel_path))
                r = self.http.get(file["url"])
                with open(abs_path, "wb") as file:
                    file.write(r.content)
