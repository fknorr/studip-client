import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import os, sys
from getpass import getpass
from errno import ENOENT
from configparser import ConfigParser
import appdirs

from parsers import *
from database import Database
from util import prompt_choice
from session import Session


def print_io_error(str, source, e):
    sys.stderr.write("Error: {} {}: {}\n".format(str, source,
            e.strerror if e.strerror else type(e).__name__))


def create_path(dir):
    try:
        os.makedirs(dir, exist_ok=True)
    except Exception as e:
        print_io_error("Unable to create directory", dir, e)
        sys.exit(1)


def setup_sync_dir():
    global command_line, sync_dir, config_file_name, db_file_name

    cache_dir = appdirs.user_cache_dir("studip", "fknorr")
    create_path(cache_dir)
    history_file_name = appdirs.user_cache_dir("studip", "fknorr") + "/history"
    history = []
    try:
        with open(history_file_name, "r", encoding="utf-8") as file:
            history = list(filter(None, file.read().splitlines()))
    except Exception:
        pass

    if "sync_dir" in command_line:
        sync_dir = command_line["sync_dir"]
    else:
        if history:
            sync_dir = history[0]
            print("Using last sync directory {} ...".format(sync_dir))
        else:
            default_dir = os.path.expanduser("~/StudIP")
            sync_dir = os.path.expanduser(input("Sync directory [{}]: ".format(default_dir)))
            if not sync_dir:
                sync_dir = default_dir

    while sync_dir in history:
        history.remove(sync_dir)
    history.insert(0, sync_dir)

    try:
        with open(history_file_name, "w", encoding="utf-8") as file:
            file.write("\n".join(history) + "\n")
    except Exception as e:
        print_io_error("Unable to write to", history_file_name, e)
        sys.exit(1)

    dot_dir = sync_dir + "/.studip"
    create_path(dot_dir)

    config_file_name = dot_dir + "/studip.conf"
    db_file_name = dot_dir + "/cache.sqlite"


def configure():
    global config, user_name, password, config_file_name

    config = ConfigParser()
    config["server"] = {
        "studip_base" : "https://studip.uni-passau.de",
        "sso_base" : "https://sso.uni-passau.de"
    }
    config["user"] = {}

    try:
        with open(config_file_name, "r", encoding="utf-8") as file:
            config.read_file(file)
    except Exception as e:
        if not (isinstance(e, IOError) and e.errno == ENOENT):
            print_io_error("Unable to read configuration from", config_file_name, e)
            sys.stderr.write("Starting over with a fresh configuration\n")

    user_config = config["user"]
    if "user_name" in user_config:
        user_name = user_config["user_name"]
    else:
        user_name = input("Stud.IP user name: ")

    if "password" in user_config:
        password = user_config["password"]
    else:
        password = getpass()

    if "save_login" in user_config and user_config["save_login"][0] in "ynu":
        save_login = user_config["save_login"][0]
    else:
        save_login = prompt_choice("Save login? ([Y]es, [n]o, [u]ser name only)", "ynu",
                default="y")
        user_config["save_login"] = { "y" : "yes", "n" : "no", "u" : "user name only" }[save_login]

    if save_login in "yu":
        user_config["user_name"] = user_name
    if save_login == "y":
        user_config["password"] = password

    try:
        with open(config_file_name, "w", encoding="utf-8") as file:
            config.write(file)
    except Exception as e:
        print_io_error("Unable to write to", config_file_name, e)
        sys.exit(1)


def open_session():
    global config, session, database, user_name, password, sync_dir

    session = Session(config, database, user_name, password, sync_dir)


def open_database():
    global database, db_file_name, config, db_file_name

    try:
        database = Database(db_file_name)
    except Exception as e:
        print_io_error("Unable to open database", db_file_name, e)
        sys.exit(1)


def update_database():
    global database, session, db_file_name

    interrupt = None
    try:
        session.update_metadata()
    except KeyboardInterrupt as e:
        interrupt = e

    database.commit()

    if interrupt:
        raise interrupt


def download_files():
    global session
    session.download_files()


def clear_cache():
    global db_file_name

    try:
        os.remove(db_file_name)
    except Exception as e:
        if not (isinstance(e, IOError) and e.errno == ENOENT):
            print_io_error("Unable to remove database file", db_file_name, e)
            sys.exit(1)

    print("Cache cleared.")


def show_usage(out):
    out.write("""Usage: {} <operation> <parameters>

Possible operations:
    update        Update course database from Stud.IP
    download      Download missing files from known database
    sync          <update>, then <download>
    clear-cache   Clear local course and file database
    help          Show this synopsis
""".format(sys.argv[0]))


def parse_command_line():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        return False

    global command_line
    command_line = {}

    op = sys.argv[1]
    if op == "help" or op == "--help" or op == "-h":
        op = "help"
    elif op not in [ "update", "download", "sync", "clear-cache" ]:
        return False
    command_line["operation"] = op

    if len(sys.argv) >= 3:
        command_line["sync_dir"] = sys.argv[2]

    return True


def main():
    global command_line

    if not parse_command_line():
        show_usage(sys.stderr)
        sys.exit(1)

    setup_sync_dir()
    configure()

    op = command_line["operation"]

    if op in [ "update", "download", "sync" ]:
        open_database()
        open_session()
        if op == "update":
            update_database()
        elif op == "download":
            download_files()
        elif op == "sync":
            update_database()
            download_files()
    elif op == "clear-cache":
        clear_cache()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
