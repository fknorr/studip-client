CREATE TABLE IF NOT EXISTS views (
    id INTEGER NOT NULL,
    name VARCHAR(30) DEFAULT "view",
    format VARCHAR(200) NOT NULL,
    base VARCHAR(40),
    esc_mode SMALLINT NOT NULL DEFAULT 1,
    charset SMALLINT NOT NULL DEFAULT 1,
    PRIMARY KEY (id asc),
    CHECK(base != "" AND base != "." AND base != "..")
);

INSERT INTO views
VALUES (0, "default", "{course} ({type})/{path}/{name}.{ext}", NULL, 1, 1);

CREATE TABLE IF NOT EXISTS semesters (
    id CHAR(32) NOT NULL,
    name VARCHAR(16) NOT NULL,
    ord INTEGER NOT NULL,
    PRIMARY KEY (id ASC)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS courses (
    id CHAR(32) NOT NULL,
    semester CHAR(32) NOT NULL,
    number VARCHAR(8) DEFAULT "",
    name VARCHAR(128) NOT NULL,
    type VARCHAR(32) NOT NULL,
    sync SMALLINT NOT NULL,
    root INTEGER,
    PRIMARY KEY (id ASC),
    FOREIGN KEY (semester) REFERENCES semesters(id),
    FOREIGN KEY (root) REFERENCES folders(id)
    CHECK (sync >= 0 AND sync <= 3) -- 3 == len(SyncMode)
) WITHOUT ROWID;

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
) WITHOUT ROWID;

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

CREATE VIEW IF NOT EXISTS folder_parents AS
    WITH RECURSIVE parents (folder, level, this, parent) AS (
        SELECT id, 0, id, parent
            FROM folders
        UNION ALL
        SELECT parents.folder, parents.level + 1, folders.id, folders.parent
            FROM folders
            INNER JOIN parents ON folders.id = parents.parent
    )
    SELECT folder, level, this FROM parents;

CREATE VIEW IF NOT EXISTS folder_paths AS
    SELECT list.folder AS folder,
        MAX(courses.id) AS course,
        '[' || IFNULL(GROUP_CONCAT('"' || REPLACE(folders.name,
            '"', '\"') || '"', ', '), '') || ']' AS path
    FROM (
        SELECT parents.folder AS folder, parents.this AS this
        FROM folder_parents AS parents
        ORDER BY level DESC
    ) AS list
    INNER JOIN folders ON folders.id = list.this
    LEFT OUTER JOIN courses ON courses.root = folders.id
    GROUP BY folder;

CREATE VIEW IF NOT EXISTS file_details AS
    SELECT f.id AS id, c.id AS course_id, s.name AS course_semester, c.name AS course_name,
            c.type AS course_type, p.path AS path, f.name AS name, f.extension AS extension,
            f.author AS author, f.description AS description, f.created AS created,
            f.copyrighted AS copyrighted, c.sync AS sync
    FROM files AS f
    INNER JOIN folder_paths AS p ON f.folder = p.folder
    INNER JOIN courses AS c ON p.course = c.id
    INNER JOIN semesters AS s ON c.semester = s.id;

CREATE VIEW IF NOT EXISTS folder_times AS
    WITH RECURSIVE ctimes (folder, time) AS (
        SELECT folder, created
            FROM files
        UNION ALL
        SELECT folders.parent, ctimes.time
            FROM folders
            INNER JOIN ctimes ON ctimes.folder = folders.id
            WHERE folders.parent IS NOT NULL
    )
    SELECT ctimes.folder, MAX(ctimes.time) AS time from ctimes
    GROUP BY folder;
