import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import json, appdirs, os, sys
from pathlib import Path
from getpass import getpass

from parsers import *


def prompt_choice(prompt, options, default=None):
    choice = None
    while choice is None or (default is None and len(choice) < 1) \
            or (len(choice) > 0 and choice[0] not in options):
        choice = input(prompt + ": ").lower()
    return choice[0] if len(choice) > 0 else default


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

    if "save_login" in config and config["save_login"][0] in "ynu":
        save_login = config["save_login"][0]
    else:
        save_login = prompt_choice("Save login? ([Y]es, [n]o, [u]ser name only)", "ynu",
                default="y")
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

    database = {
        "files" : {},
        "courses" : {}
    }

    try:
        with open(cache_dir + "/db.json", "r") as file:
            database.update(json.load(file))
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        pass


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


def ellipsize(string, length):
    if len(string) <= length:
        return string
    else:
        left = length // 2 - 2
        return string[:left] + " .. " + string[len(string)-left:]


def open_session():
    global sess, overview_page

    sess = requests.session()
    sess.get(config["studip_base"] + "/studip/index.php?again=yes&sso=shib")

    r = sess.post(config["sso_base"] + "/idp/Authn/UserPassword", data = {
        "j_username": user_name,
        "j_password": password,
        "uApprove.consent-revocation": ""
    })

    form_data = parse_saml_form(r.text)
    r = sess.post(config["studip_base"] + "/Shibboleth.sso/SAML2/POST", form_data)
    overview_page = r.text


def update_metadata():
    global sess, database, overview_page

    db_courses = database["courses"]
    db_files = database["files"]

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

        course_url = config["studip_base"] + "/studip/seminar_main.php?auswahl=" + course_id
        folder_url = config["studip_base"] + "/studip/folder.php?cid=" + course_id + "&cmd=all"

        try:
            sess.get(course_url, timeout=(None, 0))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

        r = sess.get(folder_url)
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
            r = sess.get(open_url)
            details = parse_file_details(r.text)
            if all(attr in details for attr in ["name", "url", "folder"]):
                details["course"] = course_id
                db_files[file_id] = details
                print(" " + details["description"])
            else:
                print(" <bad format>")


def update_database():
    global database

    try:
        update_metadata()
    except KeyboardInterrupt:
        write_database()
        raise
    write_database()


def download_files():
    first_file = True
    for file_id, details in database["files"].items():
        course = database["courses"][details["course"]]
        if course["sync"] == "yes":
            directory = "/".join([course["name"]] + details["folder"])
            dir_path = "/tmp/studip-client/" + directory
            os.makedirs(dir_path, exist_ok=True)
            rel_path = directory + "/" + details["name"]
            abs_path = dir_path + "/" + details["name"]
            if not os.path.isfile(abs_path):
                if first_file:
                    print()
                    first_file = False
                print("Downloading file {}...".format(rel_path))
                r = sess.get(details["url"])
                with open(abs_path, "wb") as file:
                    file.write(r.content)


def show_usage(out):
    out.write("""Usage: {} <operation> <parameters>

Possible operations:
    update      Update course database from Stud.IP
    download    Download missing files from known database
    sync        <update>, then <download>
    help        Show this synopsis
""".format(sys.argv[0]))


def execute_command_line():
    if len(sys.argv) < 2: return False

    op = sys.argv[1]
    if op == "update":
        open_session()
        update_database()
    elif op == "download":
        open_session()
        download_files()
    elif op == "sync":
        open_session()
        update_database()
        download_files()
    elif op == "help" or op == "--help" or op == "-h":
        show_usage(sys.stdout)
    else:
        return False

    return True


def main():
    configure()
    read_database()

    if not execute_command_line():
        show_usage(sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
