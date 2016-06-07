CREATE TABLE IF NOT EXISTS courses (
    id CHAR(32) NOT NULL,
    number VARCHAR(8) DEFAULT "",
    name VARCHAR(128) NOT NULL,
    sync SMALLINT NOT NULL,
    root INTEGER,
    PRIMARY KEY (id ASC),
    FOREIGN KEY (root) REFERENCES folders(id)
    CHECK (sync >= 0 AND sync <= 3) -- 3 == len(SyncMode)
);

CREATE TABLE IF NOT EXISTS files (
    id CHAR(32) NOT NULL,
    folder INTEGER NOT NULL,
    name VARCHAR(128) NOT NULL,
    extension VARCHAR(32),
    author VARCHAR(64),
    description VARCHAR(256),
    created TIMESTAMP,
    copyrighted BOOLEAN NOT NULL DEFAULT 0,
    PRIMARY KEY (id ASC),
    FOREIGN KEY (folder) REFERENCES folders(id)
);

CREATE TABLE IF NOT EXISTS folders (
    id INTEGER NOT NULL,
    name VARCHAR(128),
    parent INTEGER,
    PRIMARY KEY (id ASC),
    FOREIGN KEY (parent) REFERENCES folders(id),
    CHECK ((name IS NULL) == (parent IS NULL))
);

CREATE TRIGGER IF NOT EXISTS create_root_folder
AFTER INSERT ON courses WHEN new.root IS NULL
BEGIN
    -- INSERT INTO ... DEFAULT VALUES is not supported inside triggers
    INSERT INTO folders (parent) VALUES (NULL);
    UPDATE courses SET root = last_insert_rowid() WHERE id = new.id;
END;

CREATE VIEW IF NOT EXISTS folder_parents (folder, level, this) AS
    WITH RECURSIVE parents (folder, level, this, parent) AS (
        SELECT id, 0, id, parent
            FROM folders
        UNION ALL
        SELECT parents.folder, parents.level + 1, folders.id, folders.parent
            FROM folders
            INNER JOIN parents ON folders.id = parents.parent
    )
    SELECT folder, level, this FROM parents;

CREATE VIEW IF NOT EXISTS folder_paths (folder, course, path) AS
    SELECT list.folder, MAX(courses.id), '[' || IFNULL(GROUP_CONCAT(
        '"' || REPLACE(folders.name, '"', '\"') || '"', ', '), '') || ']'
    FROM (
        SELECT parents.folder AS folder, parents.this AS this
        FROM folder_parents AS parents
        ORDER BY level DESC
    ) AS list
    INNER JOIN folders ON folders.id = list.this
    LEFT OUTER JOIN courses ON courses.root = folders.id
    GROUP BY folder;

CREATE VIEW IF NOT EXISTS file_details (id, course_id, course_name, path, name, extension, author,
        description, created, copyrighted, sync) AS
    SELECT files.id, courses.id, courses.name, paths.path, files.name, files.extension,
            files.author, files.description, files.created, files.copyrighted, courses.sync
    FROM files
    INNER JOIN folder_paths AS paths ON files.folder = paths.folder
    INNER JOIN courses ON paths.course = courses.id;

CREATE VIEW IF NOT EXISTS folder_times (folder, time) AS
    WITH RECURSIVE ctimes (folder, time) AS (
        SELECT folder, created
            FROM files
        UNION ALL
        SELECT folders.parent, ctimes.time
            FROM folders
            INNER JOIN ctimes ON ctimes.folder = folders.id
            WHERE folders.parent IS NOT NULL
    )
    SELECT folder, MAX(time) from ctimes
    GROUP BY folder;
