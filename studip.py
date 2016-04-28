import requests
from html.parser import HTMLParser
from enum import IntEnum
import urllib.parse as urlparse
import json

from parsers import *


studip_base="https://studip.uni-passau.de"
sso_base="https://sso.uni-passau.de"

sess = requests.session()
sess.get(studip_base + "/studip/index.php?again=yes&sso=shib")

r = sess.post(sso_base + "/idp/Authn/UserPassword", data = {
    "j_username": "knorr03",
    "j_password": "Ihe4Ged6",
    "uApprove.consent-revocation": ""
})

form_data = parse_saml_form(r.text)
r = sess.post(studip_base + "/Shibboleth.sso/SAML2/POST", form_data)

database = {
    "courses" : parse_course_list(r.text),
    "files" : {}
}

i = 0
for course in database["courses"]:
    course_url = studip_base + "/studip/seminar_main.php?auswahl=" + course["id"]
    folder_url = studip_base + "/studip/folder.php?cid=" + course["id"] + "&cmd=all"

    try:
        sess.get(course_url, timeout=(None, 0))
    except:
        pass

    r = sess.get(folder_url)
    file_list = parse_file_list(r.text)

    for file_id in file_list:
        open_url = folder_url + "&open=" + file_id
        r = sess.get(open_url)
        details = parse_file_details(r.text)
        details["course"] = course["id"]
        database["files"][file_id] = details
        i += 1
        if i > 2:
            break

print(json.dumps(database, sort_keys=True, indent=4))
