BEGIN TRANSACTION;

-- Table files has a column renamed, so it must be re-created

ALTER TABLE files RENAME TO files_migrate;

DROP VIEW file_details;
DROP VIEW folder_times;

CREATE TABLE files (
    id CHAR(32) NOT NULL,
    folder INTEGER NOT NULL,
    name VARCHAR(128) NOT NULL,
    extension VARCHAR(32),
    author VARCHAR(64),
    description VARCHAR(256),
    remote_date TIMESTAMP,
    copyrighted BOOLEAN NOT NULL DEFAULT 0,
    local_date TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id ASC),
    FOREIGN KEY (folder) REFERENCES folders(id)
) WITHOUT ROWID;

INSERT INTO files (id, folder, name, extension, author, description, remote_date, copyrighted,
    local_date, version)
SELECT id, folder, name, extension, author, description, created, copyrighted, created, 0
FROM files_migrate;

DROP TABLE files_migrate;

CREATE VIEW file_details AS
    SELECT f.id AS id, c.id AS course_id, s.name AS course_semester, c.name AS course_name,
            c.type AS course_type, p.path AS path, f.name AS name, f.extension AS extension,
            f.author AS author, f.description AS description, f.remote_date AS remote_date,
            f.copyrighted AS copyrighted, f.local_date as local_date, f.version AS version,
            c.sync AS sync
    FROM files AS f
    INNER JOIN folder_paths AS p ON f.folder = p.folder
    INNER JOIN courses AS c ON p.course = c.id
    INNER JOIN semesters AS s ON c.semester = s.id;

CREATE VIEW folder_times AS
    WITH RECURSIVE ctimes (folder, time) AS (
        SELECT folder, remote_date
            FROM files
        UNION ALL
        SELECT folders.parent, ctimes.time
            FROM folders
            INNER JOIN ctimes ON ctimes.folder = folders.id
            WHERE folders.parent IS NOT NULL
    )
    SELECT ctimes.folder, MAX(ctimes.time) AS time from ctimes
    GROUP BY folder;

PRAGMA foreign_key_check;

END TRANSACTION;

