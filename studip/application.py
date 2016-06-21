import os, sys, appdirs

from getpass import getpass
from errno import ENOENT
from configparser import ConfigParser
from base64 import b64encode, b64decode

from .database import Database
from .util import prompt_choice, encrypt_password, decrypt_password
from .session import Session, SessionError, LoginError


class ApplicationExit(BaseException):
    pass


class Application:
    def print_io_error(self, msg, source, e):
        try:
            strerror = e.strerror
        except AttributeError:
            strerror = str(e)
        sys.stderr.write("Error: {} {}: {}\n".format(msg, source, strerror))


    def create_path(self, dir):
        try:
            os.makedirs(dir, exist_ok=True)
        except Exception as e:
            self.print_io_error("Unable to create directory", dir, e)
            raise ApplicationExit()


    def setup_sync_dir(self):
        self.cache_dir = appdirs.user_cache_dir("studip", "fknorr")
        self.create_path(self.cache_dir)
        history_file_name = os.path.join(appdirs.user_cache_dir("studip", "fknorr") + "history")
        history = []
        try:
            with open(history_file_name, "r", encoding="utf-8") as file:
                history = list(filter(None, file.read().splitlines()))
        except Exception:
            pass

        skipped_history = 0
        if "sync_dir" in self.command_line:
            sync_dir = self.command_line["sync_dir"]
        else:
            if history and os.path.isdir(history[0]):
                sync_dir = history[0]
                print("Using last sync directory {} ...".format(sync_dir))
            else:
                skipped_history = 1
                default_dir = "~/StudIP"
                for entry in history[1:]:
                    skipped_history += 1
                    if os.path.isdir(entry):
                        default_dir = entry

                sync_dir = input("Sync directory [{}]: ".format(default_dir))
                if not sync_dir:
                    sync_dir = default_dir

        sync_dir = os.path.abspath(os.path.expanduser(sync_dir))
        history = history[skipped_history:]
        while sync_dir in history:
            history.remove(sync_dir)

        history.insert(0, sync_dir)
        self.sync_dir = sync_dir

        try:
            with open(history_file_name, "w", encoding="utf-8") as file:
                file.write("\n".join(history) + "\n")
        except Exception as e:
            self.print_io_error("Unable to write to", history_file_name, e)
            raise ApplicationExit()

        dot_dir = os.path.join(self.sync_dir, ".studip")
        self.create_path(dot_dir)

        self.config_file_name = os.path.join(dot_dir, "studip.conf")
        self.db_file_name = os.path.join(dot_dir, "cache.sqlite")


    def save_config(self):
        try:
            with open(self.config_file_name, "w", encoding="utf-8") as file:
                self.config.write(file)
        except Exception as e:
            self.print_io_error("Unable to write to", self.config_file_name, e)
            raise ApplicationExit()


    def configure(self):
        self.config = ConfigParser()
        self.config["server"] = {
            "studip_base" : "https://studip.uni-passau.de",
            "sso_base" : "https://sso.uni-passau.de"
        }
        self.config["connection"] = {
            "update_concurrency": "4"
        }
        self.config["filesystem"] = {
            "path_format": "{course} ({type})/{path}/{name}.{ext}"
        }
        self.config["user"] = {}

        try:
            with open(self.config_file_name, "r", encoding="utf-8") as file:
                self.config.read_file(file)
        except Exception as e:
            if not (isinstance(e, IOError) and e.errno == ENOENT):
                self.print_io_error("Unable to read configuration from", config_file_name, e)
                sys.stderr.write("Starting over with a fresh configuration\n")


    def open_session(self):
        user_config = self.config["user"]
        login_changed = False

        user_secret_file_name = os.path.join(self.cache_dir, "secret")
        try:
            try:
                with open(user_secret_file_name, "rb") as file:
                    user_secret = b64decode(file.read())
            except Exception as e:
                if isinstance(e, IOError) and e.errno == ENOENT:
                    user_secret = os.urandom(50)
                    with open(user_secret_file_name, "wb") as file:
                        file.write(b64encode(user_secret) + b"\n")

                    # Any stored password is useless without a secret file
                    if "password" in user_config:
                        del user_config["password"]
                else:
                    raise
        except Exception as e:
            self.print_io_error("Unable to access", user_secret_file_name, e)
            raise ApplicationExit()

        password = None
        user_name = None
        if "user_name" in user_config:
            user_name = user_config["user_name"]
        if "password" in user_config:
            password = decrypt_password(user_secret, user_config["password"])

        while True:
            if user_name is None:
                user_name = input("Stud.IP user name: ")
                login_changed = True

            if password is None:
                password = getpass()
                login_changed = True

            try:
                self.session = Session(self.config, self.database, user_name, password,
                        self.sync_dir)
            except SessionError as e:
                sys.stderr.write("\n{}\n".format(e))
                if not isinstance(e, LoginError):
                    raise ApplicationExit()
                user_name = password = None
            else:
                break

        if login_changed:
            if "save_login" in user_config and user_config["save_login"][0] in "ynu":
                save_login = user_config["save_login"][0]
            else:
                save_login = prompt_choice("Save login? ([Y]es, [n]o, [u]ser name only)", "ynu",
                        default="y")
                user_config["save_login"] = { "y" : "yes", "n" : "no", "u" : "user name only" }[
                        save_login]

            if save_login in "yu":
                user_config["user_name"] = user_name
            if save_login == "y":
                user_config["password"] = encrypt_password(user_secret, password)

            self.save_config()


    def open_database(self):
        try:
            self.database = Database(self.db_file_name)
        except Exception as e:
            self.print_io_error("Unable to open database", self.db_file_name, e)
            raise ApplicationExit()


    def update_database(self):
        interrupt = None
        try:
            self.session.update_metadata()
        finally:
            self.database.commit()


    def download_files(self):
        self.session.download_files()


    def clear_cache(self):
        try:
            os.remove(self.db_file_name)
        except Exception as e:
            if not (isinstance(e, IOError) and e.errno == ENOENT):
                self.print_io_error("Unable to remove database file", self.db_file_name, e)
                raise ApplicationExit()

        print("Cache cleared.")


    def show_usage(self, out):
        out.write(
            "Usage: {} <operation> <parameters>\n\n"
            "Possible operations:\n"
            "    update        Update course database from Stud.IP\n"
            "    download      Download missing files from known database\n"
            "    sync          <update>, then <download>\n"
            "    clear-cache   Clear local course and file database\n"
            "    help          Show this synopsis\n"
            .format(sys.argv[0]))


    def parse_command_line(self):
        if len(sys.argv) < 2 or len(sys.argv) > 3:
            return False

        self.command_line = {}

        op = sys.argv[1]
        if op == "help" or op == "--help" or op == "-h":
            op = "help"
        elif op not in [ "update", "download", "sync", "clear-cache" ]:
            return False
        self.command_line["operation"] = op

        if len(sys.argv) >= 3:
            self.command_line["sync_dir"] = sys.argv[2]

        return True


    def run(self):
        if not self.parse_command_line():
            self.show_usage(sys.stderr)
            raise ApplicationExit()

        self.setup_sync_dir()
        self.configure()

        op = self.command_line["operation"]

        if op in [ "update", "download", "sync" ]:
            self.open_database()
            self.open_session()

            try:
                if op == "update":
                    self.update_database()
                elif op == "download":
                    self.download_files()
                elif op == "sync":
                    self.update_database()
                    self.download_files()
            except SessionError as e:
                sys.stderr.write("\n{}\n".format(e))
                raise ApplicationExit()

        elif op == "clear-cache":
            self.clear_cache()


def main():
    try:
        app = Application()
        app.run()
    except ApplicationExit:
        sys.exit(1)
    except EOFError:
        sys.stderr.write("\nError: Unexpected end of input\n")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130) # Standard UNIX exit code for SIGINT
