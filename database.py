import sqlite3
from enum import IntEnum
from collections import namedtuple


SyncMode = IntEnum("SyncMode", "NoSync Metadata Full")

class Course:
    def __init__(self, id, number=None, name=None, sync=None):
        self.id = id
        self.number = number
        self.name = name
        self.sync = sync

    def complete(self):
        return self.id and self.number and self.name and self.sync


class File:
    def __init__(self, id, course=None, path=None, name=None, created=None):
        self.id = id
        self.course = course
        self.path = path
        self.name = name
        self.created = created

    def complete(self):
        return self.id and self.course and self.path and self.name and self.created


class Folder:
    def __init__(self, id, name=None, parent=None, course=None):
        self.id = id
        self.name = name
        self.parent = parent
        self.course = course

    def complete(self):
        return self.id and self.name and (self.parent or self.course)


class QueryError(Exception):
    pass


class Database:
    def __init__(self, file_name):
        self.conn = sqlite3.connect(file_name, detect_types=sqlite3.PARSE_DECLTYPES)

        self.query_script("""
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
            """.format(len(SyncMode)+1))


    def query(self, sql, expected_rows=-1, *args, **kwargs):
        cursor = self.conn.cursor()
        if args:
            if not kwargs:
                cursor.execute(sql, (*args))
            else:
                raise ValueError("Pass either positional or keyword arguments")
        elif kwargs:
            cursor.execute(sql, dict(**kwargs))
        else:
            cursor.execute(sql)

        if expected_rows != 0:
            rows = cursor.fetchmany(expected_rows)
            if len(rows) < expected_rows:
                raise QueryError("Expected at least {} rows, got {}".format(
                        expected_rows, len(rows)))
            return rows


    def query_script(self, sql):
        self.conn.cursor().executescript(sql)


    def list_courses(self, full=False, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        sync_modes = [ str(int(enum)) for enable, enum in [ (select_sync_yes, SyncMode.Full),
                (select_sync_metadata_only, SyncMode.Metadata), (select_sync_no, SyncMode.NoSync) ]
                if enable ]

        rows = self.query("""
                SELECT {} FROM courses
                WHERE sync IN ({});
            """.format("*" if full else "id", ", ".join(sync_modes)))

        if full:
            return [ Course(id, number, name, SyncMode(sync)) for id, number, name, sync in rows ]
        else:
            return [ id for (id,) in rows ]


    def get_course_details(self, course_id):
        rows = self.query("""
                SELECT number, name, sync
                FROM courses
                WHERE courses.id = :id;
            """, id=course_id, expected_rows=1)
        number, name, sync = rows[0]
        return Course(id=course_id, number=number, name=name, sync=SyncMode(sync))


    def add_course(self, course):
        self.query("""
                INSERT INTO courses
                VALUES (:id, :num, :name, :sync);
            """, id=course.id, num=course.number, name=course.name, sync=int(course.sync),
                expected_rows=0)


    def delete_course(self, course):
        self.query("""
                DELETE FROM courses
                WHERE id = :id;
            """, id=course.id, expected_rows=0)


    def list_files(self, full=False, select_sync_yes=True, select_sync_metadata_only=True,
            select_sync_no=True):
        Mode = SyncMode
        sync_modes = [ str(int(enum)) for enable, enum in [ (select_sync_yes, SyncMode.Full),
                (select_sync_metadata_only, SyncMode.Metadata), (select_sync_no, SyncMode.NoSync) ]
                if enable ]

        rows = self.query("""
                SELECT files.id FROM files
                INNER JOIN folders ON files.folder = folders.id
                INNER JOIN courses ON folders.course = courses.id
                WHERE courses.sync IN ({});
            """.format(", ".join(sync_modes)))
        return [id for (id,) in rows]


    def add_file(self, file):
        rows = self.query("""
                SELECT id FROM folders
                WHERE course = :course AND name = :name
            """, course=file.course, name=file.path[0])
        if not rows:
            self.query("""
                    INSERT INTO folders (name, course)
                    VALUES (:name, :course)
                """, name=file.path[0], course=file.course, expected_rows=0)
            rows = self.query("""
                    SELECT id FROM folders
                    WHERE course = :course AND name = :name
                """, course=file.course, name=file.path[0])
        parent, = rows[0]


        for folder in file.path[1:]:
            rows = self.query("""
                    SELECT id FROM folders
                    WHERE parent = :par AND name = :name
                """, par=parent, name=file.course)
            if not rows:
                self.query("""
                        INSERT INTO folders (name, parent)
                        VALUES(:name, :par)
                    """, name=folder, par=parent, expected_rows=0)

        self.query("""
                INSERT INTO files (id, folder, name, created)
                VALUES (:id, :par, :name, :creat);
            """, id=file.id, par=parent, name=file.name, creat=file.created, expected_rows=0)

    def commit(self):
        self.conn.commit()

