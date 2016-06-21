from base64 import b64encode, b64decode

def prompt_choice(prompt, options, default=None):
    choice = None
    while choice is None or (default is None and len(choice) < 1) \
            or (len(choice) > 0 and choice[0] not in options):
        choice = input(prompt + ": ").lower()
    return choice[0] if len(choice) > 0 else default


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

