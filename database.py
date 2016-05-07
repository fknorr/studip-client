import sqlite3
from enum import IntEnum


class Database:
    SyncMode = IntEnum("SyncMode", "None Metadata Full")

    def __init__(self, config, file_name):
        self.config = config
        self.conn = sqlite3.connect(file_name)

        c = self.conn.cursor()
        c.executescript("""
                CREATE TABLE IF NOT EXISTS courses (
                    id CHAR(32) NOT NULL,
                    number VARCHAR(8) DEFAULT "",
                    name VARCHAR(128) NOT NULL,
                    sync SMALLINT NOT NULL,
                    PRIMARY KEY (id ASC),
                    CHECK (sync >= 0 AND sync < {})
                );
                CREATE TABLE IF NOT EXISTS files (
                    id CHAR(32) NOT NULL,
                    folder INTEGER NOT NULL,
                    PRIMARY KEY (id ASC),
                    FOREIGN KEY (folder) REFERENCES folders(id)
                );
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER NOT NULL,
                    name VARCHAR(128),
                    parent INTEGER DEFAULT NULL,
                    course char(32) NOT NULL,
                    PRIMARY KEY (id ASC),
                    FOREIGN KEY (course) REFERENCES courses(id)
                    FOREIGN KEY (parent) REFERENCES folders(id)
                );
            """.format(len(Database.SyncMode)))
        self.conn.commit()

    def list_courses(self, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        Mode = Database.SyncMode
        sync_modes = [ int(enum) for enable, enum in [ (select_sync_yes, Mode.Full),
                (select_sync_metadata_only, Mode.Metadata), (select_sync_no, Mode.None) if enable ]

        c = self.conn.cursor()
        rows = c.execute("""
                SELECT files.id
                    FROM files
                INNER JOIN folders
                    ON files.folder = folders.id
                INNER JOIN courses
                    ON folders.course = courses.id
                WHERE courses.sync IN ({})
            """.format(", ".join(sync_modes))
        return [id for (id,) in rows]

    def get_course_details(self, course):
        c = self.conn.cursor()
        # Concatenate the path using a recursive query
        # http://stackoverflow.com/questions/24253999/using-sqlites-new-with-recursive-cte-clause

    def add_course(self, id, course):
        self["courses"][id] = course

    def delete_course(self, course):
        del self["courses"][course]
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

