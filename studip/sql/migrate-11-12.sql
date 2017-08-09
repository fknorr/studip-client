BEGIN TRANSACTION;

DROP VIEW file_details;

ALTER TABLE courses
ADD COLUMN abbrev VARCHAR(12);

ALTER TABLE courses
ADD COLUMN type_abbrev VARCHAR(4);

CREATE VIEW file_details AS
    SELECT f.id AS id, c.id AS course_id, s.name AS course_semester, c.name AS course_name,
            c.abbrev AS course_abbrev, c.type AS course_type, c.type_abbrev as course_type_abbrev,
            p.path AS path, f.name AS name, f.extension AS extension,
            f.author AS author, f.description AS description, f.remote_date AS remote_date,
            f.copyrighted AS copyrighted, f.local_date as local_date, f.version AS version,
            c.sync AS sync
    FROM files AS f
    INNER JOIN folder_paths AS p ON f.folder = p.folder
    INNER JOIN courses AS c ON p.course = c.id
    INNER JOIN semesters AS s ON c.semester = s.id;

COMMIT TRANSACTION;

