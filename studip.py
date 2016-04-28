#!/usr/bin/env python3

import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import json, appdirs, os, sys
from pathlib import Path
from getpass import getpass

from parsers import *


def configure():
    global config, user_name, password

    config_dir = appdirs.user_config_dir("studip-client", "fknorr")
    os.makedirs(config_dir, exist_ok=True)
    config_file_name = config_dir + "/config.json"

    config = {
        "studip_base" : "https://studip.uni-passau.de",
        "sso_base" : "https://sso.uni-passau.de"
    }

    try:
        with open(config_file_name, "r") as file:
            config.update(json.load(file))
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        pass

    if "user_name" in config:
        user_name = config["user_name"]
    else:
        user_name = input("User name: ")

    if "password" in config:
        password = config["password"]
    else:
        password = getpass()

    if "save_login" in config:
        save_login = config["save_login"]
    else:
        choice = ""
        while len(choice) < 1 or choice[0] not in "ynu":
            choice = input("Save login? ([y]es, [n]o, [u]ser name only): ").lower()
        save_login = choice[0]
        config["save_login"] = { "y" : "yes", "n" : "no", "u" : "user name only" }[save_login];

    if save_login in "yu":
        config["user_name"] = user_name
    if save_login == "y":
        config["password"] = password

    try:
        with open(config_file_name, "w") as file:
            json.dump(config, file, indent=4)
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        sys.stderr.write("Unable to write to {}\n".format(config_file_name))
        sys.exit(1)


def read_database():
    global db_file_name, database

    cache_dir = appdirs.user_cache_dir("studip-client", "fknorr")
    os.makedirs(cache_dir, exist_ok = True)
    db_file_name = cache_dir + "/db.json"

    try:
        with open(cache_dir + "/db.json", "r") as file:
            database = json.load(file)
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        database = {
            "files" : {}
        }


def write_database():
    global db_file_name, database

    try:
        with open(db_file_name, "w") as file:
            json.dump(database, file, indent=4)
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        sys.stderr.write("Unable to write to {}\n".format(db_file_name))
        sys.exit(1)


def main():
    configure()
    read_database()

    sess = requests.session()
    sess.get(config["studip_base"] + "/studip/index.php?again=yes&sso=shib")

    r = sess.post(config["sso_base"] + "/idp/Authn/UserPassword", data = {
        "j_username": user_name,
        "j_password": password,
        "uApprove.consent-revocation": ""
    })

    form_data = parse_saml_form(r.text)
    r = sess.post(config["studip_base"] + "/Shibboleth.sso/SAML2/POST", form_data)
    if not "courses" in database:
        database["courses"] = parse_course_list(r.text)

    i = 0
    for course in database["courses"]:
        course_url = config["studip_base"] + "/studip/seminar_main.php?auswahl=" + course["id"]
        folder_url = config["studip_base"] + "/studip/folder.php?cid=" + course["id"] + "&cmd=all"

        try:
            sess.get(course_url, timeout=(None, 0))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

        r = sess.get(folder_url)
        file_list = parse_file_list(r.text)

        for file_id in file_list:
            if file_id not in database["files"]:
                open_url = folder_url + "&open=" + file_id
                r = sess.get(open_url)
                details = parse_file_details(r.text)
                details["course"] = course["id"]
                database["files"][file_id] = details
                i += 1
                if i > 2:
                    break

    write_database()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
