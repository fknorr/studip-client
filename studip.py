import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import json, appdirs, os, sys
from pathlib import Path
from getpass import getpass
from errno import ENOENT

from parsers import *
from database import Database
from util import prompt_choice


def configure():
    global command_line, config, user_name, password

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

    if "sync_dir" in command_line and command_line["sync_dir"] is None:
        if "sync_dir" in config:
            command_line["sync_dir"] = config["sync_dir"]
        else:
            default_dir = os.path.expanduser("~/StudIP")
            sync_dir = input("Sync directory [{}]: ".format(default_dir))
            if not sync_dir:
                sync_dir = default_dir
            config["sync_dir"] = sync_dir
            command_line["sync_dir"] = sync_dir

    if "user_name" in config:
        user_name = config["user_name"]
    else:
        user_name = input("Stud.IP user name: ")

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


def open_session():
    global config, session, overview_page

    session = requests.session()
    session.get(config["studip_base"] + "/studip/index.php?again=yes&sso=shib")

    r = session.post(config["sso_base"] + "/idp/Authn/UserPassword", data = {
        "j_username": user_name,
        "j_password": password,
        "uApprove.consent-revocation": ""
    })

    form_data = parse_saml_form(r.text)
    r = session.post(config["studip_base"] + "/Shibboleth.sso/SAML2/POST", form_data)
    overview_page = r.text


def read_database():
    global database, db_file_name, config

    cache_dir = appdirs.user_cache_dir("studip-client", "fknorr")
    os.makedirs(cache_dir, exist_ok = True)
    db_file_name = cache_dir + "/db.json"

    database = Database(config)

    try:
        database.read(db_file_name)
    except IOError as e:
        if e.errno != ENOENT:
            sys.stderr.write("Error: Unable to read from {}: {}\n".format(db_file_name, e.strerror))
            sys.exit(1)


def update_database():
    global database, session, overview_page, db_file_name

    interrupt = None
    try:
        database.fetch(session, overview_page)
    except KeyboardInterrupt as e:
        interrupt = e

    try:
        database.write(db_file_name)
    except IOError as e:
        sys.stderr.write("Error: Unable to write to {}: {}\n".format(db_file_name, e.strerror))
        sys.exit(1)

    if interrupt:
        raise interrupt


def download_files():
    global command_line, database

    first_file = True
    for file_id, details in database["files"].items():
        course = database["courses"][details["course"]]
        if course["sync"] == "yes":
            directory = "/".join([course["name"]] + details["folder"])
            dir_path = command_line["sync_dir"] + "/" + directory
            os.makedirs(dir_path, exist_ok=True)
            rel_path = directory + "/" + details["name"]
            abs_path = dir_path + "/" + details["name"]
            if not os.path.isfile(abs_path):
                if first_file:
                    print()
                    first_file = False
                print("Downloading file {}...".format(rel_path))
                r = session.get(details["url"])
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


def parse_command_line():
    if len(sys.argv) < 2: return False

    global command_line
    command_line = {}

    op = sys.argv[1]
    if op == "update":
        if len(sys.argv) != 2: return False
    elif op == "download" or op == "sync":
        if len(sys.argv) > 3: return False
        command_line["sync_dir"] = sys.argv[2] if len(sys.argv) == 3 else None
    elif op == "help" or op == "--help" or op == "-h":
        op = "help"
    else:
        return False

    command_line["operation"] = op
    return True


def main():
    global command_line

    if not parse_command_line():
        show_usage(sys.stderr)
        sys.exit(1)

    configure()
    read_database()
    open_session()

    op = command_line["operation"]
    if op == "update":
        update_database()
    elif op == "download":
        download_files()
    elif op == "sync":
        update_database()
        download_files()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
