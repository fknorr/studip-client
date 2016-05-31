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
    SELECT list.folder, MAX(courses.id), GROUP_CONCAT(folders.name, '/')
    FROM (
        SELECT parents.folder AS folder, parents.this AS this
        FROM folder_parents AS parents
        ORDER BY level DESC
    ) AS list
    INNER JOIN (
        SELECT id, CASE WHEN folders.name IS NOT NULL THEN folders.name ELSE '' END AS name
        FROM folders
    ) AS folders ON folders.id = list.this
    LEFT OUTER JOIN courses ON courses.root = folders.id
    GROUP BY folder;

CREATE VIEW IF NOT EXISTS folder_parent_paths (folder, course, level, path) AS
    SELECT parents.folder, paths.course, parents.level, paths.path
    FROM folder_parents AS parents
    INNER JOIN folder_paths AS paths ON parents.this = paths.folder;

CREATE VIEW IF NOT EXISTS file_paths (file, course, path) AS
    SELECT files.id, paths.course, paths.path
    FROM files
    INNER JOIN folder_paths AS paths ON files.folder = paths.folder;

CREATE VIEW IF NOT EXISTS file_parent_paths (file, course, level, path) AS
    SELECT files.id, paths.course, paths.level, paths.path
    FROM files
    INNER JOIN folder_parent_paths AS paths ON files.folder = paths.folder;

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
