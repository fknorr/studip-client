import os, sys, appdirs, stat

from getpass import getpass
from base64 import b64encode, b64decode
from errno import ENOENT

from .config import Config
from .database import Database, View, QueryError, SyncMode
from .util import prompt_choice, expand_int_range, encrypt_password, decrypt_password, Charset, \
        EscapeMode, ellipsize
from .session import Session, SessionError, LoginError
from .views import ViewSynchronizer


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
        history_file_name = os.path.join(appdirs.user_cache_dir("studip", "fknorr"), "history")
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

        self.dot_dir = os.path.join(self.sync_dir, ".studip")
        self.create_path(self.dot_dir)

        self.config_file_name = os.path.join(self.dot_dir, "studip.conf")
        self.db_file_name = os.path.join(self.dot_dir, "cache.sqlite")


    def configure(self):
        self.config = Config(self.config_file_name, {
                ("server", "studip_base"): "https://studip.uni-passau.de",
                ("server", "sso_base"): "https://sso.uni-passau.de",
                ("connection", "update_concurrency"): 4
            })


    def open_session(self):
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
                    if ("user", "password") in self.config:
                        del self.config["user", "password"]
                else:
                    raise
        except Exception as e:
            self.print_io_error("Unable to access", user_secret_file_name, e)
            raise ApplicationExit()

        password = None
        user_name = None
        if ("user", "user_name") in self.config:
            user_name = self.config["user", "user_name"]
        if ("user", "password") in self.config:
            password = decrypt_password(user_secret, self.config["user", "password"])

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
            if ("user", "save_login") in self.config \
                    and self.config["user", "save_login"][0] in "ynu":
                save_login = self.config["user", "save_login"][0]
            else:
                save_login = prompt_choice("Save login? ([Y]es, [n]o, [u]ser name only)", "ynu",
                        default="y")
                self.config["user", "save_login"] \
                        = { "y" : "yes", "n" : "no", "u" : "user name only" }[save_login]

            if save_login in "yu":
                self.config["user", "user_name"] = user_name
            if save_login == "y":
                self.config["user", "password"] = encrypt_password(user_secret, password)


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


    def fetch_files(self):
        self.session.fetch_files()


    def checkout(self):
        for view in self.database.list_views(full=True):
            sync = ViewSynchronizer(self.sync_dir, self.config, self.database, view)
            sync.checkout()


    def clear_cache(self):
        try:
            os.remove(self.db_file_name)
        except Exception as e:
            if not (isinstance(e, IOError) and e.errno == ENOENT):
                self.print_io_error("Unable to remove database file", self.db_file_name, e)
                raise ApplicationExit()

        print("Cache cleared.")


    def gc(self):
        files_dir = os.path.join(self.dot_dir, "files")
        removed_files = 0
        for f in os.listdir(files_dir):
            path = os.path.join(files_dir, f)
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode) and st.st_nlink < 2:
                try:
                    os.unlink(path)
                    removed_files += 1
                except IOError as e:
                    self.print_io_error("Unable to remove cached file", path, e)
        print("Removed {} stale file(s)".format(removed_files))


    def edit_views(self):
        views = self.database.list_views(full=True)

        view_op = self.command_line["view_op"]

        if view_op == "list":
            name_width = max(len("name"), max(len(v.name) for v in views))
            base_width = max(len("base"), max(len(v.base) if v.base else 0 for v in views))
            format_width = max(len("format"), max(len(v.format) for v in views))
            fmt = "{{:{}}} | {{:{}}} | {{:{}}} | {{:8}} | {{:9}}".format(name_width, base_width,
                    format_width, )
            print(fmt.format("name", "base", "format", "escape", "charset"))
            print(fmt.format("", "", "", "", "").replace(" ", "-").replace("|", "+"))
            for v in views:
                print(fmt.format(v.name, v.base if v.base else "/", v.format,
                    {
                        EscapeMode.Similar: "similar",
                        EscapeMode.Typeable: "typeable",
                        EscapeMode.CamelCase: "camel",
                        EscapeMode.SnakeCase: "snake"
                    }[v.escape],
                    {
                        Charset.Unicode: "unicode",
                        Charset.Ascii: "ascii",
                        Charset.Identifier: "identifier"
                    }[v.charset]))
            return

        if view_op == "reset-deleted" and "view_name" not in self.command_line:
            for v in views:
                sync = ViewSynchronizer(self.sync_dir, self.config, self.database, v)
                sync.reset_deleted()
            return

        matching_views = [v for v in views if v.name == self.command_line["view_name"]]

        if view_op == "add" and matching_views or view_op != "add" and not matching_views:
            fmt = "{}: no such view\n" if view_op != "add" else "{}: view already exists\n"
            sys.stderr.write(fmt.format(self.command_line["view_name"]))
            raise ApplicationExit()

        elif view_op == "add":
            id = max(v.id for v in views) + 1 if views else 0
            view = View(id, self.command_line["view_name"])
            for key, value in self.command_line["view_sets"]:
                if key == "format":
                    view.format = value
                elif key == "base":
                    if value in [ "", ".", ".." ]:
                        view.base = None
                    else:
                        view.base = value
                elif key == "escape":
                    try:
                        view.escape = {
                            "similar": EscapeMode.Similar,
                            "typeable": EscapeMode.Typeable,
                            "camel": EscapeMode.CamelCase,
                            "snake": EscapeMode.SnakeCase
                        }[value];
                    except:
                        sys.stderr.write("No such escape mode: {}\n".format(value))
                        raise ApplicationExit
                elif key == "charset":
                    try:
                        view.charset = {
                            "unicode": Charset.Unicode,
                            "ascii": Charset.Ascii,
                            "identifier": Charset.Identifier
                        }[value];
                    except:
                        sys.stderr.write("No such charset: {}\n".format(value))
                        raise ApplicationExit
                else:
                    sys.stderr.write("Unknown key \"{}\"\n".format(key))
                    raise ApplicationExit

            if views and (view.base is None
                    or any(v.base is None or v.base == view.base for v in views)):
                sys.stderr.write("View base folders cannot have any kind of subdirectory "
                        "relationship. You probably want to remove the 'default' view first.\n")
                raise ApplicationExit

            self.database.add_view(view)
        else:
            view = matching_views[0]
            if view_op == "rm":
                view_sync = ViewSynchronizer(self.sync_dir, self.config, self.database, view)
                view_sync.remove()
                self.database.remove_view(view.id)
            else: # view_op == "reset-deleted"
                view_sync = ViewSynchronizer(self.sync_dir, self.config, self.database, view)
                view_sync.reset_deleted()

        self.database.commit()


    def show_course_table(self, courses):
        abbrev_width = max(len("abbrev"), max(len(c.abbrev) for c in courses)+1)
        fmt = "{:3} | {:" + str(abbrev_width) + "} | {:50} | {:7} | {:25} | {:4}"
        print(fmt.format("", "abbrev", "name", "tabbrev", "type", "sync"))
        print(fmt.format("", "", "", "", "", "").replace(" ", "-").replace("|", "+"))
        for i, c in enumerate(courses):
            print(fmt.format(i+1, c.abbrev + ("*" if c.auto_abbrev else ""), ellipsize(c.name, 50),
                    c.type_abbrev + ("*" if c.auto_type_abbrev else ""), ellipsize(c.type, 25),
                    "yes" if c.sync == SyncMode.Full else "no"))


    def edit_courses(self):
        courses = self.database.list_courses(full=True)

        course_op = self.command_line["course_op"]
        if course_op == "list":
            self.show_course_table(courses)
        else:
            if len(self.database.list_views(full=False)):
                print("Error: Please remove all views before editing course metadata.")
                raise ApplicationExit()

            try:
                course_range = expand_int_range(self.command_line["course_range"], 1, len(courses))
            except ValueError:
                print("Error: Invalid course range.")
                raise ApplicationExit()

            for num in course_range:
                course = courses[num-1]
                if course_op == "sync":
                    course.sync = SyncMode.Full if self.command_line["course_sync"] \
                            else SyncMode.NoSync
                elif course_op == "set-name":
                    old_auto_abbrev = course.abbrev if course.auto_abbrev else None
                    course.name = self.command_line["course_new_id"]
                    if old_auto_abbrev and course.abbrev != old_auto_abbrev:
                        print("{} {}: Auto-generated name abbreviation changed from \"{}\"to \"{}\"".format(
                            course.name, course.type, old_auto_abbrev, course.abbrev))
                elif course_op == "set-type":
                    old_auto_abbrev = course.type_abbrev if course.auto_type_abbrev else None
                    course.type = self.command_line["course_new_id"]
                    if old_auto_type_abbrev and course.type_abbrev != old_auto_type_abbrev:
                        print("{} {}: Auto-generated type abbreviation changed from \"{}\" to \"{}\"".format(
                            course.name, course.type, old_auto_type_abbrev, course.type_abbrev))
                elif course_op == "set-abbrev":
                    course.abbrev = self.command_line["course_new_id"]
                elif course_op == "set-tabbrev":
                    course.type_abbrev = self.command_line["course_new_id"]
                self.database.update_course(course)

            self.database.commit()


    def show_usage(self, out):
        out.write(
            "Usage: {} <operation> <parameters>\n"
            "\nSynchronization operations:\n"
            "    update        Update course database from Stud.IP\n"
            "    fetch         Download missing files from known database\n"
            "    checkout      Checkout files into views\n"
            "    sync          <update>, then <fetch>, then <checkout>\n"
            "    gc            Delete fetched files that are not checked out\n"
            "    clear-cache   Clear local course and file database\n"
            "\nCommands for showing and modifying views:\n"
            "    view list\n"
            "    view add <name> [<key> <value>]...\n"
            "    view rm [-f] <name>\n"
            "    view reset-deleted [<name>]\n"
            "\nCommands for showing and changing courses:\n"
            "    course list\n"
            "    course sync <range> yes|no\n"
            "    course set-name <range> <new-name>\n"
            "    course set-abbrev <range> <new-abbrev>\n"
            "    course set-type <range> <new-type>\n"
            "    course set-tabbrev <range> <new-type-abbrev>\n"
            "    ... where <range> is similar to \"1,3-5,7-9\"\n"
            "\nGeneral commands:\n"
            "    help          Show this synopsis\n"
            "\nPossible global parameters:\n"
            "    -d <dir>      Sync directory, assuming most recent one if not given\n"
            .format(sys.argv[0]))


    def parse_command_line(self):
        if len(sys.argv) < 2:
            return False

        self.command_line = {}

        args = sys.argv[1:]
        if args[0] == "help" or "--help" in args or "-h" in args:
            self.command_line["operation"] = "help"
            return True

        plain = []
        i = 0
        while i < len(args):
            if args[i].startswith("-"):
                if args[i] == "-d" and i < len(args)-1:
                    self.command_line["sync_dir"] = args[i+1]
                    i += 1
                else:
                    return False
            else:
                plain.append(args[i])
            i += 1

        if not plain: return False
        op = plain[0]
        plain = plain[1:]

        if op in [ "update", "fetch", "checkout", "sync", "clear-cache", "gc" ]:
            if len(plain) > 0:
                return False
        elif op == "view":
            if len(plain) < 1:
                return False
            else:
                self.command_line["view_op"] = view_op = plain[0]
                if view_op == "list":
                    if len(plain) != 1:
                        return False
                elif view_op in [ "add", "rm", "reset-deleted" ]:
                    if len(plain) > 1:
                        self.command_line["view_name"] = plain[1]
                    elif view_op not in [ "reset-deleted" ]:
                        return False
                    self.command_line["view_sets"] = []
                    if len(plain) > 2:
                        if view_op == "add" and len(plain) % 2 == 0:
                            for i in range(2, len(plain), 2):
                                self.command_line["view_sets"].append((plain[i], plain[i+1]))
                        else:
                            return False
                else:
                    return False
        elif op == "course":
            if len(plain) < 1:
                return False
            else:
                self.command_line["course_op"] = course_op = plain[0]
                if course_op in [ "list" ]:
                    if len(plain) != 1:
                        return False
                elif course_op in [ "sync", "set-name", "set-abbrev", "set-type",
                        "set-tabbrev" ]:
                    if len(plain) != 3:
                        return False
                    self.command_line["course_range"] = plain[1]
                    if course_op == "sync":
                        value = plain[2].lower()
                        if value in [ "yes", "true", "on" ]:
                            self.command_line["course_sync"] = SyncMode.Full
                        elif value in [ "no", "false", "off" ]:
                            self.command_line["course_sync"] = SyncMode.NoSync
                        else:
                            return False
                    elif course_op in [ "set-name", "set-abbrev", "set-type", "set-tabbrev" ]:
                        self.command_line["course_new_id"] = plain[2]
                else:
                    return False
        else:
            return False

        self.command_line["operation"] = op
        return True


    def run(self):
        if not self.parse_command_line():
            self.show_usage(sys.stderr)
            raise ApplicationExit()

        self.setup_sync_dir()

        op = self.command_line["operation"]

        if op in [ "update", "fetch", "checkout", "sync", "view", "course" ]:
            self.configure()
            with self.config:
                self.open_database()

                if op in [ "update", "fetch", "sync" ]:
                    self.open_session()
                    try:
                        if op == "update":
                            self.update_database()
                        elif op == "fetch":
                            self.fetch_files()
                        elif op == "sync":
                            self.update_database()
                            self.fetch_files()
                            self.checkout()
                    except SessionError as e:
                        sys.stderr.write("\n{}\n".format(e))
                        raise ApplicationExit()

                elif op == "checkout":
                    self.checkout()
                elif op == "view":
                    self.edit_views()
                elif op == "course":
                    self.edit_courses()
        elif op == "clear-cache":
            self.clear_cache()
        elif op == "gc":
            self.gc()
        else: # op == "help"
            self.show_usage(sys.stdout)


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
