import re

from base64 import b64encode, b64decode
from enum import IntEnum

INT_RANGE_SEP_RE = re.compile(r"[.;,:\s]+")
INT_RANGE_INTERVAL_RE = re.compile(r"(\d+)(\s*-\s*(\d+))?")
PUNCTUATION_WHITESPACE_RE = re.compile(r"[ _/.,;:\-_#'+*~!^\"$%&/()[\]}{\\?<>|]+")
NON_ASCII_RE = re.compile(r"[^\x00-\x7f]+")
NON_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]+")
FS_SPECIAL_CHARS_RE = re.compile(r"[/:]+")
WORD_SEPARATOR_RE = re.compile(r'[-. _/()]+')
NUMBER_RE = re.compile(r'^([0-9]+)|([IVXLCDM]+)$')
SEMESTER_RE = re.compile(r'^(SS|WS) (\d{2})(.(\d{2}))?')


def prompt_choice(prompt, options, default=None):
    choice = None
    while choice is None or (default is None and len(choice) < 1) \
            or (len(choice) > 0 and choice[0] not in options):
        choice = input(prompt + ": ").lower()
    return choice[0] if len(choice) > 0 else default


def expand_int_range(range_str, low, high):
    """Takes a range string such as 1,3-5 7-9", expanding it to [1, 3, 4, 5, 7, 8, 9]"""
    # Split into intervals ["1", "3-5", "7-9"]
    intervals = INT_RANGE_SEP_RE.split(range_str)
    if not intervals: return []
    nums = []
    for iv in intervals:
        # Can either be a single number "1" or an interval "3-5"
        match = INT_RANGE_INTERVAL_RE.match(iv)
        if not match:
            raise ValueError("Invalid integer range")
        lower = int(match.group(1))
        upper = int(match.group(3)) if match.group(2) else lower
        nums += range(lower, upper+1)
    return nums


def ellipsize(string, length):
    if len(string) <= length:
        return string
    else:
        return string[:length - 3] + "..."

def xor_bytes(key, text):
    while len(key) < len(text): key += key
    return bytearray(a^b for a, b in zip(text, key))


def encrypt_password(secret, password):
    password_code = str(len(password)) + ":" + password
    password_code += "." * (30 - (len(password_code)+1) % 30 - 1)
    return b64encode(xor_bytes(secret, password_code.encode("utf-8"))).decode("ascii")


def decrypt_password(secret, crypt):
    try:
        password_code = xor_bytes(secret, b64decode(crypt.encode("ascii"))).decode("utf-8")
        length, password = tuple(password_code.split(":", 2))
        return password[:int(length)]
    except Exception:
        return None


def compact(str):
    return " ".join(str.split())


def chunks(list, count):
    chunk_size = len(list) // count
    modulo = len(list) % count
    offset = 0
    for i in range(count):
        yield list[offset : offset + chunk_size + (1 if i < modulo else 0)]


EscapeMode = IntEnum("EscapeMode", "Similar Typeable CamelCase SnakeCase")
Charset = IntEnum("Charset", "Unicode Ascii Identifier")

def escape_file_name(str, charset, mode):
    if charset in [Charset.Ascii, Charset.Identifier]:
        str = str.replace("ß", "ss").replace("ä", "ae").replace("Ä", "Ae") \
                .replace("ö", "oe").replace("Ö", "Oe").replace("ü", "ue") \
                .replace("Ü", "Ue")
        str = (NON_ASCII_RE if charset == Charset.Ascii else NON_IDENTIFIER_RE).sub("", str)
    if mode in [EscapeMode.SnakeCase, EscapeMode.CamelCase] or charset == Charset.Identifier:
        parts = PUNCTUATION_WHITESPACE_RE.split(str)
        if mode == EscapeMode.SnakeCase:
            return "_".join(parts).lower()
        elif mode == EscapeMode.CamelCase:
            return "".join(w[0].upper() + w[1:] for w in parts if len(w) > 0)
        else:
            return "_".join(parts)
    elif mode == EscapeMode.Typeable or charset in [Charset.Ascii, Charset.Identifier]:
        return FS_SPECIAL_CHARS_RE.sub("-" if charset == Charset.Ascii else "_", str)
    else: # mode == "unicode" or incorrectly set
        # Replace regular '/' by similar looking 'DIVISION SLASH' (U+2215) and ':' by
        # 'RATIO' to create a valid directory name
            return str.replace("/", "\u2215").replace(":", "\u2236")


def abbreviate_course_name(name):
    words = WORD_SEPARATOR_RE.split(name)
    number = ""
    abbrev = ""
    if len(words) > 1 and NUMBER_RE.match(words[-1]):
        number = words[-1]
        words = words[0:len(words) - 1]
    if len(words) < 3:
        abbrev = "".join(w[0 : min(3, len(w))] for w in words)
    elif len(words) >= 3:
        abbrev = "".join(w[0] for w in words if len(w) > 0)
    return abbrev + number


def abbreviate_course_type(type):
    special_abbrevs = {
        "Arbeitsgemeinschaft": "AG",
        "Studien-/Arbeitsgruppe": "SG",
    }
    try:
        return special_abbrevs[type]
    except KeyError:
        abbrev = type[0]
        if type.endswith("seminar"):
            abbrev += "S"
        return abbrev


def lexicalise_semester(semester, short=False):
    """Takes input of the form "SS 16" or "WS 16/17" and converts it to "2016SS" or "2016WS17"."""
    if short:
        return SEMESTER_RE.sub(r'20\2\1', semester)
    else:
        return SEMESTER_RE.sub(r'20\2\1\4', semester)


