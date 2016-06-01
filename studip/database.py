import sqlite3, os
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
    def __init__(self, id, course=None, course_name=None, path=None, name=None, author=None,
            description=None, created=None, copyrighted=False):
        self.id = id
        self.course = course
        self.course_name = course_name
        self.path = path
        self.name = name
        self.author = author
        self.description = description
        self.created = created
        self.copyrighted = copyrighted

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
    schema_version = 2

    def __init__(self, file_name):
        def connect(self):
            self.conn = sqlite3.connect(file_name, detect_types=sqlite3.PARSE_DECLTYPES)

        # Try using the existing db, if the version differs from the internal schema version,
        # delete the database and start over
        connect(self)
        db_version, = self.query("PRAGMA user_version", expected_rows=1)[0]
        if db_version != self.schema_version:
            if db_version != 0:
                self.conn.close()
                print("Clearing cache: DB file version out of date")
                os.remove(file_name)
                connect(self)

            # At this point, the database is definitely empty.
            self.query("PRAGMA user_version = " + str(self.schema_version), expected_rows=0)

            # Create all tables, views and triggers
            script_dir = os.path.dirname(os.path.realpath(__file__))
            with open(script_dir + "/setup.sql", "r") as file:
                init_script = file.read()

            self.query_script(init_script)


    def query(self, sql, expected_rows=-1, *args, **kwargs):
        cursor = self.conn.cursor()
        if args:
            if not kwargs:
                cursor.execute(sql, tuple(*args))
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
            """.format("id, number, name, sync" if full else "id", ", ".join(sync_modes)))

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
                INSERT INTO courses (id, number, name, sync)
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

        if full:
            rows = self.query("""
                    SELECT files.id, courses.id, courses.name, file_paths.path, files.name,
                        files.author, files.description, files.created, files.copyrighted
                    FROM file_paths
                    INNER JOIN files ON file_paths.file = files.id
                    INNER JOIN courses ON file_paths.course = courses.id
                    WHERE courses.sync IN ({});
                """.format(", ".join(sync_modes)))
            return [ File(*r) for r in rows ]

        else:
            rows = self.query("""
                    SELECT file_paths.file FROM file_paths
                    INNER JOIN courses ON file_paths.course = courses.id
                    WHERE courses.sync IN ({});
                """.format(", ".join(sync_modes)))
            return [id for (id,) in rows]


    def add_file(self, file):
        rows = self.query("""
                SELECT root FROM courses
                WHERE id = :course
            """, course=file.course)
        parent, = rows[0]

        for folder in file.path:
            def query_subdirectory():
                return self.query("""
                        SELECT id FROM folders
                        WHERE parent = :par AND name = :name
                    """, par=parent, name=folder)

            rows = query_subdirectory()
            if not rows:
                self.query("""
                        INSERT INTO folders (name, parent)
                        VALUES(:name, :par)
                    """, name=folder, par=parent, expected_rows=0)
                rows = query_subdirectory()
            parent, = rows[0]

        self.query("""
                INSERT INTO files (id, folder, name, author, description, created, copyrighted)
                VALUES (:id, :par, :name, :auth, :descr, :creat, :copy);
            """, id=file.id, par=parent, name=file.name, auth=file.author, descr=file.description,
            creat=file.created, copy=file.copyrighted, expected_rows=0)


    def list_file_parent_dirs(self, file):
        rows = self.query("""
                SELECT courses.name || paths.path
                FROM file_parent_paths AS paths
                INNER JOIN courses ON paths.course = courses.id
                WHERE paths.file = :file
            """, file=file)
        return [ path for path, in rows ]

    def commit(self):
        self.conn.commit()

