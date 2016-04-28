import requests
from html.parser import HTMLParser
from enum import IntEnum

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

State = IntEnum("State", "before_sem before_thead_end before_tr \
    tr td_group td_img td_id td_name after_td after_sem")

class SeminarListParser(HTMLParser):
    state = State.before_sem
    seminars = []

    def handle_starttag(self, tag, attrs):
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
        if self.state == State.td_id:
            self.current_id += data
        elif self.state == State.td_name:
            self.current_name += data

sem_parser = SeminarListParser()
sem_parser.feed(r.text)
seminars = sem_parser.seminars

class OverviewParser(HTMLParser):
    folder_url = ""
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            if "href" in attrs and "folder.php" in attrs["href"]:
                self.folder_url = attrs["href"]

for sem in seminars:
    r = sess.get(sem["url_overview"])
    overview_parser = OverviewParser()
    overview_parser.feed(r.text)
    sem["url_files"] = overview_parser.folder_url

for sem in seminars:
    print(sem)
