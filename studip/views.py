import os,time

from os import path

from .util import ellipsize, escape_file_name


class ViewSynchronizer:
    def __init__(self, sync_dir, config, db):
        self.sync_dir = sync_dir
        self.meta_dir = path.join(self.sync_dir, ".studip")
        self.files_dir = path.join(self.meta_dir, "files")
        self.config = config
        self.db = db

        self.existing_files = []
        for file in self.db.list_files(full=True, select_sync_metadata_only=False,
                select_sync_no=False):
            abs_path = path.join(self.files_dir, file.id)
            if path.isfile(abs_path):
                file.inode = os.lstat(abs_path).st_ino
                self.existing_files.append(file)

    def checkout(self, view):
        first_file = True
        modified_folders = set()
        copyrighted_files = []

        view_dir = path.join(self.sync_dir, view.base if view.base else "")
        fs_escape = lambda str: escape_file_name(str, view.charset, view.escape)

        def format_path(tokens):
            try:
                return view.format.format(**tokens)
            except Exception:
                raise SessionError("Invalid path format: " + path_format)

        try:
            for i, file in enumerate(self.existing_files):
                def make_path(folders):
                    return path.join(*map(fs_escape, folders)) if folders else ""

                descr_no_ext = file.description
                if descr_no_ext.endswith("." + file.extension):
                    descr_no_ext = descr_no_ext[:-1-len(file.extension)]

                short_path = file.path
                if short_path[0] == "Allgemeiner Dateiordner":
                    short_path = short_path[1:]

                tokens = {
                    "semester": file.course_semester,
                    "course-id": file.course,
                    "course": fs_escape(file.course_name),
                    "type": fs_escape(file.course_type),
                    "path": make_path(file.path),
                    "short-path": make_path(short_path),
                    "id": file.id,
                    "name": fs_escape(file.name),
                    "ext": file.extension,
                    "description": fs_escape(file.description),
                    "descr-no-ext": fs_escape(descr_no_ext),
                    "author": fs_escape(file.author),
                    "time": fs_escape(str(file.created))
                }

                rel_path = format_path(tokens)

                # First update modified_folders, then create directories.
                folder = path.dirname(rel_path)
                while folder:
                    modified_folders.add(folder)
                    folder = path.dirname(folder)
                
                abs_path = path.join(view_dir, rel_path)
                os.makedirs(path.dirname(abs_path), exist_ok=True)

                if not path.isfile(abs_path):
                    if first_file:
                        print()
                        first_file = False
                    print("Checking out file {}/{}: {}...".format(i, len(self.existing_files),
                            ellipsize(file.description, 50)))

                    if file.copyrighted:
                        copyrighted_files.append(rel_path)

                    os.link(path.join(self.files_dir, file.id), abs_path)

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
                update_directory_mtime(path.join(view_dir, folder))
            if view.base:
                update_directory_mtime(view_dir)
            update_directory_mtime(self.sync_dir)

            if copyrighted_files:
                print("\n" + "-"*80)
                print("The following files have special copyright notices:\n")
                for file in copyrighted_files:
                    print("  -", file)
                print("\nPlease make sure you have looked up, read and understood the terms and"
                        " conditions of these files before proceeding to use them.")
                print("-"*80 + "\n")

        # Create course folders for all courses that do not have files yet
        for course in self.db.list_courses(full=True, select_sync_metadata_only=False,
                select_sync_no=False):
            # Construct a dummy file for extracting the fromatted path
            tokens = {
                "semester": course.semester,
                "course-id": course,
                "course": fs_escape(course.name),
                "type": fs_escape(course.type),
                "path": "",
                "short-path": "",
                "id": "0" * 32,
                "name": "dummy",
                "ext": "txt",
                "description": "dummy.txt",
                "descr-no-ext": "dummy",
                "author": "A",
                "time": fs_escape(str(time.localtime()))
            }

            abs_path = path.join(view_dir, format_path(tokens))

            try:
                os.makedirs(path.dirname(abs_path), exist_ok=True)
                print("Created folder for empty {} {}".format(course.type, course.name))
            except OSError: # Folder already exists
                pass


    def remove(self, view, force=False):
        view_dir = path.join(self.sync_dir, view.base if view.base else "")

        # Remove our files, mark directories containing foreign files
        directories = []
        directories_to_keep = []
        for cwd, dirs, files in os.walk(view_dir):
            if cwd.startswith(self.meta_dir): continue

            has_foreign_files = False
            for lf in files:
                # Is this file a hardlink to a file we control?
                abs_path = os.path.join(cwd, lf)
                inode = os.lstat(abs_path).st_ino
                if any(f.inode == inode for f in self.existing_files):
                    os.unlink(abs_path)
                else:
                    has_foreign_files = True

            directories += [path.join(cwd, d) for d in dirs if d != ".studip"]
            if has_foreign_files:
                directories_to_keep.append(cwd)

        # Sort descending by length so that subdirectories appear before their parents
        directories.sort(key=len, reverse=True)

        # Remove empty directories
        for dir in directories:
            if not any (d.startswith(dir) for d in directories_to_keep):
                os.rmdir(dir)

        if directories_to_keep:
            print("The following directories contain unmanaged files and were kept:\n  - "
                    + "\n  - ".join(directories_to_keep))
        else:
            os.rmdir(view_dir)
