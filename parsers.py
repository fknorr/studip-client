import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse


def get_url_field(url, field):
    parsed_url = urlparse.urlparse(url)
    query = urlparse.parse_qs(parsed_url.query, encoding="iso-8859-1")
    return query[field][0] if field in query else None


def create_parser_and_feed(parser_class, html):
    parser = parser_class()
    parser.feed(html)
    return parser


class SAMLFormParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "name" in attrs and "value" in attrs:
            if attrs["name"] == "RelayState":
                self.relay_state = attrs["value"]
            elif attrs["name"] == "SAMLResponse":
                self.saml_response = attrs["value"]

    def form_data(self):
        return { "RelayState" : self.relay_state, "SAMLResponse" : self.saml_response }

def parse_saml_form(html):
    return create_parser_and_feed(SAMLFormParser, html).form_data()


class CourseListParser(HTMLParser):
    State = IntEnum("State", "before_sem before_thead_end before_tr \
        tr td_group td_img td_id td_name after_td after_sem")

    def __init__(self):
        super().__init__()
        State = CourseListParser.State
        self.state = State.before_sem
        self.courses = []

    def handle_starttag(self, tag, attrs):
        State = CourseListParser.State
        if self.state == State.before_sem:
            if tag == "div" and ("id", "my_seminars") in attrs:
                self.state = State.before_thead_end
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
            self.state = State.after_sem
        elif self.state == State.before_thead_end:
            if tag == "thead":
                self.state = State.before_tr
        elif self.state == State.after_td:
            if tag == "tr":
                self.courses.append({
                    "number" : ' '.join(self.current_number.split()),
                    "id": self.current_id,
                    "name": ' '.join(self.current_name.split())
                })
                self.state = State.before_tr

    def handle_data(self, data):
        State = CourseListParser.State
        if self.state == State.td_id:
            self.current_number += data
        elif self.state == State.td_name:
            self.current_name += data

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
    State = IntEnum("State", "outside file_0_div in_header_span in_open_div in_folder_a")

    def __init__(self):
        super().__init__()
        State = FileDetailsParser.State
        self.state = State.outside
        self.div_depth = 0
        self.file = {}

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
                    elif "sendfile.php" in href:
                        self.file["url"] = href

    def handle_endtag(self, tag):
        State = FileDetailsParser.State
        if tag == "div" and self.state in [ State.file_0_div, State.in_open_div ]:
            if self.div_depth > 0:
                self.div_depth -= 1
        elif tag == "a" and self.state == State.in_folder_a:
            self.state = State.in_open_div
        elif tag == "span" and self.state == State.in_header_span:
            self.state = State.in_open_div

    def handle_data(self, data):
        State = FileDetailsParser.State
        if self.state == State.in_folder_a:
            self.file["folder"] = data.split(sep=" / ")
        elif self.state == State.in_header_span:
            self.file["description"] = data

def parse_file_details(html):
    return create_parser_and_feed(FileDetailsParser, html).file
