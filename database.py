import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import json, appdirs, os, sys
from pathlib import Path
from getpass import getpass

from parsers import parse_course_list, parse_file_list, parse_file_details
from util import prompt_choice, ellipsize


class Database(dict):
    def __init__(self, config):
        super().__init__({
            "files" : {},
            "courses" : {}
        })
        self.config = config

    def read(self, file_name):
        with open(file_name, "r") as file:
            self.update(json.load(file))


    def write(self, file_name):
        with open(file_name, "w") as file:
            json.dump(self, file, indent=4)


    def fetch(self, session, overview_page):
        db_courses = self["courses"]
        db_files = self["files"]

        remote_courses = parse_course_list(overview_page)

        new_courses = (course for course in remote_courses if course not in db_courses)
        removed_courses = (course for course in db_courses if course not in remote_courses)

        for course in removed_courses:
            choice = prompt_choice("Delete data for removed course \"{}\"? ([Y]es, [n]o)".format(
                    ellipsize(course["name"], 50)), "yn", default="y")
            if choice == "y":
                del db_courses[course]
                for file_id, details in db_files:
                    if details["course"] == course:
                        del db_files[file_id]

        for course_id in new_courses:
            course = remote_courses[course_id]
            sync = prompt_choice("Synchronize \"{}\"? ([Y]es, [n]o, [m]etadata only)".format(
                    ellipsize(course["name"], 50)), "ynm", default="y")
            course["sync"] = { "y" : "yes", "n" : "no", "m" : "metadata only" }[sync]
            db_courses[course_id] = course

        sync_courses = (course for course in db_courses if db_courses[course]["sync"] != "no")
        last_course_synced = False
        for course_id in sync_courses:
            course = db_courses[course_id]

            base_url = self.config["studip_base"] + "/studip"
            course_url = base_url + "/seminar_main.php?auswahl=" + course_id
            folder_url = base_url + "/folder.php?cid=" + course_id + "&cmd=all"

            try:
                session.get(course_url, timeout=(None, 0))
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                pass

            r = session.get(folder_url)
            file_list = parse_file_list(r.text)

            if last_course_synced:
                print()

            new_files = [file_id for file_id in file_list if file_id not in db_files]
            if len(new_files) > 0 :
                if not last_course_synced:
                    print()
                print(len(new_files), end="")
                last_course_synced = True
            else:
                print("No", end="")
                last_course_synced = False
            print(" new files for " + course["name"])

            for i, file_id in enumerate(new_files):
                print("Fetching metadata for file {}/{}...".format(i+1, len(new_files)),
                        end="", flush=True)

                open_url = folder_url + "&open=" + file_id
                r = session.get(open_url)
                details = parse_file_details(r.text)
                if all(attr in details for attr in ["name", "url", "folder"]):
                    details["course"] = course_id
                    db_files[file_id] = details
                    print(" " + details["description"])
                else:
                    print(" <bad format>")

