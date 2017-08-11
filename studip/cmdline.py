import sys
from collections import namedtuple


class CommandLineError(Exception):
    pass


Option = namedtuple("Option", "short long argument")


class CommandLineParser:
    commands = []
    opts = []

    def command(self, name):
        cmd = CommandLineParser()
        self.commands[name] = cmd
        return cmd

    def option(self, long, short, argument, help):
        self.opts.append({ "long": long, "short": short, "argument": argument, "help": help })

    def parse(self, argv=None):
        if argv is None:
            argv = sys.argv

        cmd = []
        options = []

        path = [self]
        i = 1
        while i < len(argv):
            arg = argv[i]
            if arg.startswith("-"):
                if arg.startswith("--"):
                    parts = [p.trim() for p in arg[2:].split("=", 2)]
                    long = parts[0]

                    matching_opt = None
                    for c in path:
                        matches = [o for o in c.opts if o["long"] == long]
                        if matches:
                            matching_opt = matches[0]
                            break

                    if matching_opt is None:
                        raise CommandLineError("Unknown option --" + long)

                    if matching_opt["argument"]:
                        if len(parts) == 2:
                            argument = parts[1]
                        elif i+1 < len(argv) and not argv[i+1].startswith("-"):
                            argument = argv[i+1]
                            i += 1
                        else:
                            raise CommandLineError("Missing argument for option --" + long)
                    else:
                        if len(parts) == 1:
                            argument = None
                        else:
                            raise CommandLineError("Unexpected argument for option --" + long)

                    options.append(long, matching_opt["short"], argument)
                else:
                    short_args = list(arg[1:])

                    matching_opts = []
                    for c in path:
                        matches = [o for o in c.opts if o["short"] in short_args
                                and o not in matching_opts]
                        for m in matches:
                            if len(short_args) > 1 and m["argument"]:
                                raise CommandLineError("Option -{} used in a option group, "
                                        + "but it requires an argument".format(m["short"]))
                        matching_opts += matches

                    if len(matching_opts) < len(short_args):
                        first_unmatched = next(a for a in short_args if not (
                                o for o in matching_opts if o["short"] == a["short"]))
                        raise CommandLineError("Unknown option -" + first_unmatched["short"])

                    if len(matching_opts) == 1 and matching_opts[0]["argument"]:
                        if i+1 < len(argv) and not argv[i+1].startswith("-"):
                            options = [Option(matching_opts[0]["long"],
                                    matching_opts[0]["short"], argv[i+1])]
                            i += 1
                        else:
                            raise CommandLineError("Missing argument for option --" + long)
                    else:
                        options = [Option(o["long"], o["short"], None) for o in matching_opts]
            else: # not arg.startswith("-")
                cmd.append(arg)
        return (cmd, options)
                    
