import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse

studip_base="https://studip.uni-passau.de"
sso_base="https://sso.uni-passau.de"

sess = requests.session()
sess.get(studip_base + "/studip/index.php?again=yes&sso=shib")

data = {
    "j_username": "knorr03",
    "j_password": "Ihe4Ged6",
    "uApprove.consent-revocation": ""
}
r = sess.post(sso_base + "/idp/Authn/UserPassword", data=data)

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

saml = SAMLFormParser()
saml.feed(r.text)

r = sess.post(studip_base + "/Shibboleth.sso/SAML2/POST", saml.form_data())

class SeminarListParser(HTMLParser):
    State = IntEnum("State", "before_sem before_thead_end before_tr \
        tr td_group td_img td_id td_name after_td after_sem")

    def __init__(self):
        super().__init__()
        State = SeminarListParser.State
        self.state = State.before_sem
        self.seminars = []

    def handle_starttag(self, tag, attrs):
        State = SeminarListParser.State
        if self.state == State.before_sem:
            if tag == "div" and ("id", "my_seminars") in attrs:
                self.state = State.before_thead_end
        elif self.state == State.before_tr and tag == "tr":
            self.state = State.tr
            self.current_url = self.current_id = self.current_name = ""
            self.current_seminar = { "id": "", "name" : "" } 
        elif tag == "td" and self.state in [ State.tr, State.td_group, State.td_img, State.td_id,
                State.td_name ]:
            self.state = State(int(self.state) + 1)
        elif self.state == State.td_name and tag == "a":
            attrs = dict(attrs)
            self.current_url = attrs["href"]

    def handle_endtag(self, tag):
        State = SeminarListParser.State
        if tag == "div" and self.state != State.before_sem:
            self.state = State.after_sem
        elif self.state == State.before_thead_end:
            if tag == "thead":
                self.state = State.before_tr
        elif self.state == State.after_td:
            if tag == "tr":
                self.state = State.before_tr
                self.seminars.append({
                    "id" : ' '.join(self.current_id.split()),
                    "url_overview": self.current_url,
                    "name": ' '.join(self.current_name.split())
                })

    def handle_data(self, data):
        State = SeminarListParser.State
        if self.state == State.td_id:
            self.current_id += data
        elif self.state == State.td_name:
            self.current_name += data


sem_parser = SeminarListParser()
sem_parser.feed(r.text)
seminars = sem_parser.seminars


class OverviewParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.folder_url = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            if "href" in attrs and "folder.php" in attrs["href"]:
                self.folder_url = attrs["href"]
                

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
                    parsed_file_url = urlparse.urlparse(attrs["href"])
                    query = urlparse.parse_qs(parsed_file_url.query, encoding="iso-8859-1")
                    if "file_id" in query:
                        self.file_ids.append(query["file_id"][0])

    def handle_endtag(self, tag):
        State = FileListParser.State
        if tag == "div" and self.state == State.file_0_div:
            if self.div_depth > 0:
                self.div_depth -= 1    
            else:
                self.state = State.outside


class FileDetailsParser(HTMLParser):
    State = IntEnum("State", "outside file_0_div in_open_div in_folder_a")

    def __init__(self, file_id):
        super().__init__()
        State = FileDetailsParser.State
        self.state = State.outside
        self.div_depth = 0
        self.file = { "file_id" : file_id, "folder" : [] }

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
                self.state = State.in_open_div
        elif self.state == State.in_open_div:
            if tag == "a":
                attrs = dict(attrs)
                if "href" in attrs and "folder.php" in attrs["href"]:
                    self.state = State.in_folder_a

    def handle_endtag(self, tag):
        State = FileDetailsParser.State
        if tag == "div" and self.state in [ State.file_0_div, State.in_open_div ]:
            if self.div_depth > 0:
                self.div_depth -= 1    
        elif tag == "a" and self.state == State.in_folder_a:
            self.state = State.in_open_div

    def handle_data(self, data):
        State = FileDetailsParser.State
        if self.state == State.in_folder_a:
            self.file["folder"].append(data)


for sem in seminars:
    r = sess.get(sem["url_overview"])
    overview_parser = OverviewParser()
    overview_parser.feed(r.text)
    if overview_parser.folder_url:
        sem["url_files"] = overview_parser.folder_url + "&cmd=all"

    if "url_files" in sem:
        url = sem["url_files"]
        r = sess.get(url)
        list_parser = FileListParser()
        list_parser.feed(r.text)

        for file_id in list_parser.file_ids:
            open_url = url + "&open=" + file_id
            r = sess.get(open_url)
            details_parser = FileDetailsParser(file_id)
            details_parser.feed(r.text)
            print(details_parser.file)
        
