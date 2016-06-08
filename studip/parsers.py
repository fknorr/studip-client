import requests, re
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
from datetime import datetime

from .database import Semester, Course, SyncMode, File
from .util import compact


def get_url_field(url, field):
    parsed_url = urlparse.urlparse(url)
    query = urlparse.parse_qs(parsed_url.query, encoding="iso-8859-1")
    return query[field][0] if field in query else None


class ParserError(Exception):
    def __init__(self, message=""):
        self.message = message

    def __repr__(self):
        return "ParserError({})".format(repr(self.message))


class StopParsing(Exception):
    pass


def create_parser_and_feed(parser_class, html):
    parser = parser_class()
    try:
        parser.feed(html)
    except StopParsing:
        pass

    return parser


class SAMLFormParser(HTMLParser):
    fields = [ "RelayState", "SAMLResponse" ]

    def __init__(self):
        super().__init__()
        self.form_data = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "name" in attrs and "value" in attrs:
            if attrs["name"] in SAMLFormParser.fields:
                self.form_data[attrs["name"]] = attrs["value"]
        if self.is_complete():
            raise StopParsing

    def is_complete(self):
        return all(f in self.form_data for f in SAMLFormParser.fields)

def parse_saml_form(html):
    parser = create_parser_and_feed(SAMLFormParser, html)
    if parser.is_complete():
        return parser.form_data
    else:
        raise ParserError("SAMLForm")


class SemesterListParser(HTMLParser):
    State = IntEnum("State", "outside select optgroup option")

    def __init__(self):
        super().__init__()
        self.state = SemesterListParser.State.outside
        self.semesters = []
        self.selected = None
        self.current_id = None
        self.current_name = ""

    def handle_starttag(self, tag, attrs):
        State = SemesterListParser.State
        if tag == "select":
            attrs = dict(attrs)
            if self.state == State.outside and "name" in attrs and attrs["name"] == "sem_select":
                self.state = State.select
        if tag == "optgroup" and self.state == State.select:
            self.state = State.optgroup
        if tag == "option":
            attrs = dict(attrs)
            if self.state == State.select and "selected" in attrs and "value" in attrs:
                self.selected = attrs["value"]
            elif self.state == State.optgroup and "value" in attrs:
                self.current_id = attrs["value"]
                self.state = State.option

    def handle_endtag(self, tag):
        State = SemesterListParser.State
        if tag == "select" and self.state == State.select:
            raise StopParsing()
        if tag == "optgroup" and self.state == State.optgroup:
            self.state = State.select
        if tag == "option" and self.state == State.option:
            self.state = State.optgroup
            self.semesters.append(Semester(self.current_id, name=compact(self.current_name)))
            self.current_name = ""

    def handle_data(self, data):
        State = SemesterListParser.State
        if self.state == State.option:
            self.current_name += data


def parse_semester_list(html):
    parser = create_parser_and_feed(SemesterListParser, html)
    for i, sem in enumerate(parser.semesters):
        sem.order = len(parser.semesters) - 1 - i
    return parser


class CourseListParser(HTMLParser):
    State = IntEnum("State", "before_sem before_thead_end table_caption before_tr "
        "tr td_group td_img td_id td_name after_td")

    def __init__(self):
        super().__init__()
        State = CourseListParser.State
        self.state = State.before_sem
        self.courses = []
        self.current_id = None
        self.current_number = None
        self.current_name = None

    def handle_starttag(self, tag, attrs):
        State = CourseListParser.State
        if self.state == State.before_sem:
            if tag == "div" and ("id", "my_seminars") in attrs:
                self.state = State.before_thead_end
        elif self.state == State.before_thead_end:
            if tag == "caption":
                self.state = State.table_caption
                self.current_semester = ""
        elif self.state == State.before_tr and tag == "tr":
            self.state = State.tr
            self.current_url = self.current_number = self.current_name = ""
        elif tag == "td" and self.state in [ State.tr, State.td_group, State.td_img, State.td_id,
                State.td_name ]:
            self.state = State(int(self.state) + 1)
        elif self.state == State.td_name and tag == "a":
            attrs = dict(attrs)
            self.current_id = get_url_field(attrs["href"], "auswahl")

    def handle_endtag(self, tag):
        State = CourseListParser.State
        if tag == "div" and self.state != State.before_sem:
            raise StopParsing
        elif self.state == State.before_thead_end:
            if tag == "thead":
                self.state = State.before_tr
        elif self.state == State.table_caption:
            if tag == "caption":
                self.state = State.before_thead_end
        elif self.state == State.after_td:
            if tag == "tr":
                full_name = compact(self.current_name)
                name, type = re.match("(.*?)\s*\(\s*([^)]+)\s*\)\s*$", full_name).groups()
                self.courses.append(Course(id=self.current_id,
                        semester=compact(self.current_semester),
                        number=compact(self.current_number),
                        name=name, type=type, sync=SyncMode.NoSync))
                self.state = State.before_tr

    def handle_data(self, data):
        State = CourseListParser.State
        if self.state == State.td_id:
            self.current_number += data
        elif self.state == State.td_name:
            self.current_name += data
        elif self.state == State.table_caption:
            self.current_semester += data

def parse_course_list(html):
    return create_parser_and_feed(CourseListParser, html).courses


class OverviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.locations = {}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            if "href" in attrs and "folder.php" in attrs["href"]:
                self.locations["folder_url"] = attrs["href"]

def parse_overview(html):
    return create_parser_and_feed(OverviewParser, html).locations


class FileListParser(HTMLParser):
    State = IntEnum("State", "outside file_0_div")

    def __init__(self):
        super().__init__()
        State = FileListParser.State
        self.state = State.outside
        self.div_depth = 0
        self.file_ids = []

    def handle_starttag(self, tag, attrs):
        State = FileListParser.State
        if self.state == State.outside and tag == "div":
            attrs = dict(attrs)
            if "id" in attrs and attrs["id"].startswith("file_") and attrs["id"].endswith("_0"):
                self.state = State.file_0_div
                self.div_depth = 0
        elif self.state == State.file_0_div:
            attrs = dict(attrs)
            if tag == "div":
                self.div_depth += 1
            if tag == "a":
                if "href" in attrs and "sendfile.php" in attrs["href"]:
                    file_id = get_url_field(attrs["href"], "file_id")
                    if file_id:
                        self.file_ids.append(file_id)

    def handle_endtag(self, tag):
        State = FileListParser.State
        if tag == "div" and self.state == State.file_0_div:
            if self.div_depth > 0:
                self.div_depth -= 1
            else:
                self.state = State.outside

def parse_file_list(html):
    return create_parser_and_feed(FileListParser, html).file_ids


class FileDetailsParser(HTMLParser):
    State = IntEnum("State", "outside file_0_div in_header_span in_open_div in_folder_a "
            "after_header_span in_origin_td in_author_a")

    def __init__(self):
        super().__init__()
        State = FileDetailsParser.State
        self.state = State.outside
        self.div_depth = 0
        self.file = File(None)
        self.current_date = ""

    def handle_starttag(self, tag, attrs):
        State = FileDetailsParser.State
        if self.state == State.outside and tag == "div":
            attrs = dict(attrs)
            if "id" in attrs and attrs["id"].startswith("file_") and attrs["id"].endswith("_0"):
                self.current_file = {}
                self.state = State.file_0_div
                self.div_depth = 0
        elif self.state == State.file_0_div:
            attrs = dict(attrs)
            if tag == "div":
                self.div_depth += 1
            elif tag == "span" and "id" in attrs and attrs["id"].endswith("_header") \
                    and "style" in attrs and "bold" in attrs["style"]:
                self.state = State.in_header_span
        elif self.state == State.in_open_div:
            if tag == "a":
                attrs = dict(attrs)
                if "href" in attrs:
                    href = attrs["href"]
                    if "folder.php" in href:
                        self.state = State.in_folder_a
                    elif "sendfile.php" in href and not "zip=" in href:
                        self.file.id = get_url_field(href, "file_id")
                        file_name_parts = get_url_field(href, "file_name").rsplit(".", 1)
                        self.file.name = file_name_parts[0]
                        if len(file_name_parts) > 0:
                            self.file.extension = file_name_parts[1]
            if tag == "div":
                attrs = dict(attrs)
                if "class" in attrs and "messagebox" in attrs["class"]:
                    self.file.copyrighted = True
        elif self.state == State.after_header_span and tag == "td":
            self.state = State.in_origin_td
        elif self.state == State.in_origin_td and tag == "a":
            self.state = State.in_author_a

    def handle_endtag(self, tag):
        State = FileDetailsParser.State
        if tag == "div" and self.state in [ State.file_0_div, State.in_open_div ]:
            if self.div_depth > 0:
                self.div_depth -= 1
            elif self.file.id is not None:
                raise StopParsing()
        elif tag == "a" and self.state == State.in_folder_a:
            self.state = State.in_open_div
        elif tag == "span" and self.state == State.in_header_span:
            self.state = State.after_header_span
        elif tag == "a" and self.state == State.in_author_a:
            self.state = State.in_origin_td
        elif tag == "td" and self.state == State.in_origin_td:
            self.state = State.in_open_div
            date_str = compact(self.current_date)
            try:
                self.file.created = datetime.strptime(date_str, "%d.%m.%Y - %H:%M")
            except ValueError:
                pass

    def handle_data(self, data):
        State = FileDetailsParser.State
        if self.state == State.in_folder_a:
            self.file.path = data.split(sep=" / ")
        elif self.state == State.in_header_span:
            self.file.description = data
        elif self.state == State.in_origin_td:
            self.current_date += data
        elif self.state == State.in_author_a:
            self.file.author = data

def parse_file_details(course_id, html):
    file = create_parser_and_feed(FileDetailsParser, html).file
    file.course = course_id
    if file.complete():
        return file
    else:
        raise ParserError("FileDetails")
