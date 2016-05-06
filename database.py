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

    def list_courses(self, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        return [id for id, c in self["courses"].items() \
                if (select_sync_yes and c["sync"] == "yes") \
                or (select_sync_metadata_only and c["sync"] == "metadata only") \
                or (select_sync_no and c["sync"] == "no")]

    def get_course_details(self, course):
        return self["courses"][course]

    def add_course(self, id, course):
        self["courses"][id] = course

    def delete_course(self, course):
        del self["courses"][course];
        for id, file in self["files"].items():
            if file["course"] == course:
                del self["files"][id]

    def list_files(self):
        return list(self["files"].keys())

    def list_file_details(self, sync_courses_only=False):
        details = []
        for id, file in self["files"].items():
            course = self["courses"][file["course"]]
            if not sync_courses_only or course["sync"] == "yes":
                entry = file
                entry["id"] = id
                entry["path"] = course["name"] + "/" + "/".join(entry["folder"])
                details.append(entry)
        return details

    def add_file(self, id, file):
        self["files"][id] = file

