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
        left = length // 2 - 2
        return string[:left] + " .. " + string[len(string)-left:]

