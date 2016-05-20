import sqlite3
from enum import IntEnum
from collections import namedtuple


SyncMode = IntEnum("SyncMode", "None Metadata Full")
Course = namedtuple("Course", [ "id", "number", "name", "sync" ])
File = namedtuple("File", [ "id", "course", "path", "name", "created" ])
Folder = namedtuple("Folder", [ "id", "name", "parent", "course" ])


class Database:

    def __init__(self, config, file_name):
        self.config = config
        self.conn = sqlite3.connect(file_name, detect_types=sqlite3.PARSE_DECLTYPES)

        self.conn.cursor().executescript("""
                CREATE TABLE IF NOT EXISTS courses (
                    id CHAR(32) NOT NULL,
                    number VARCHAR(8) DEFAULT "",
                    name VARCHAR(128) NOT NULL,
                    sync SMALLINT NOT NULL,
                    PRIMARY KEY (id ASC),
                    CHECK (sync >= 0 AND sync < ?)
                );
                CREATE TABLE IF NOT EXISTS files (
                    id CHAR(32) NOT NULL,
                    folder INTEGER NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    created TIMESTAMP,
                    PRIMARY KEY (id ASC),
                    FOREIGN KEY (folder) REFERENCES folders(id)
                );
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER NOT NULL,
                    name VARCHAR(128),
                    parent INTEGER,
                    course char(32),
                    PRIMARY KEY (id ASC),
                    FOREIGN KEY (course) REFERENCES courses(id),
                    FOREIGN KEY (parent) REFERENCES folders(id),
                    CHECK ((parent IS NULL) != (course IS NULL))
                );
                CREATE VIEW IF NOT EXISTS file_paths(id, path) AS
                    WITH RECURSIVE parent_dir(file, level, parent, name) AS (
                        SELECT files.id, 0, folders.parent, folders.name FROM folders
                            INNER JOIN files ON files.folder = folders.id
                        UNION ALL
                        SELECT parent_dir.file, parent_dir.level + 1, folders.parent,
                                folders.name FROM folders
                            INNER JOIN parent_dir ON folders.id = parent_dir.parent
                    )
                    SELECT file, GROUP_CONCAT(name, '/') FROM (
                        SELECT * FROM parent_dir ORDER BY level DESC
                    ) GROUP BY (file);
            """, len(Database.SyncMode))
        self.conn.commit()


    def list_courses(self, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        Mode = Database.SyncMode
        sync_modes = [ int(enum) for enable, enum in [ (select_sync_yes, Mode.Full),
                (select_sync_metadata_only, Mode.Metadata), (select_sync_no, Mode.None) if enable ]

        rows = self.conn.cursor().execute("""
                SELECT id FROM courses
                WHERE sync IN (?);
            """., ", ".join(sync_modes))
        return [id for (id,) in rows]


    def get_course_details(self, course_id):
        rows = self.conn.cursor().execute("""
                SELECT number, name, sync
                FROM courses
                WHERE courses.id = '?';
            """, course_id)
        number, name, sync = rows[0]
        return Course(id=course_id, number=number, name=name, sync=SyncMode(sync))


    def add_course(self, course):
        self.conn.cursor().execute("""
                INSERT INTO courses
                VALUES ('?', '?', '?' '?');
            """, (course.id, course.number, course.name, int(course.sync)))


    def delete_course(self, course):
        self.conn.cursor().execute("""
                DELETE FROM courses
                WHERE id = '?';
            """, course.id)


    def list_all_files(self, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        Mode = Database.SyncMode
        sync_modes = [ int(enum) for enable, enum in [ (select_sync_yes, Mode.Full),
                (select_sync_metadata_only, Mode.Metadata), (select_sync_no, Mode.None) if enable ]

        rows = self.conn.cursor().execute("""
                SELECT files.id FROM files
                INNER JOIN folders ON files.folder = folders.id
                INNER JOIN courses ON folders.course = courses.id
                WHERE courses.sync IN (?);
            """., ", ".join(sync_modes))
        return [id for (id,) in rows]


    def add_file(self, id, file):
        self.conn.cursor().execute("""
                INSERT INTO files (id, name, created)
                VALUES ('?', '?', '?');
            """);

    def commit(self):
        self.conn.commit()

