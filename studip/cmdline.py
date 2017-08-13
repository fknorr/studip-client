import sys
from collections import namedtuple


class CommandLine:
    def __init__(self, command, options):
        self.command = command
        self.options = options

    def __getitem__(self, key):
        try:
            return next(o for o in self.options if o.short == key)
        except ValueError:
            return next(o for o in self.options if o.long == key)


class CommandLineError(Exception):
    pass


Option = namedtuple("Option", "short long argument")


class CommandLineParser:
    def __init__(self, require_command=False):
        self.commands = {}
        self.opts = []
        self.require_command = require_command


    def command(self, name, require_subcommand=False):
        if name is None:
            raise ValueError("name must not be None")
        if name in self.commands:
            raise ValueError("command {} already defined in {}".format(name, self.commands))

        cmd = CommandLineParser(require_subcommand)
        self.commands[name] = cmd
        return cmd


    def option(self, long, short, argument, help):
        if short is None and long is None:
            raise ValueError("Either short or long must be defined")
        if short is not None and len(short) != 1:
            raise ValueError("If defined, the short option name must be one character long")

        self.opts.append({ "long": long, "short": short, "argument": argument, "help": help })


    def parse(self, argv=None):
        if argv is None:
            argv = sys.argv
        if argv is None or len(argv) < 1:
            raise CommandLineError("Empty command line")

        cmd = []
        options = []

        path = [self]
        i = 1

        def parse_long(arg):
            parts = [p.strip() for p in arg[2:].split("=", 2)]
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

            options.append(Option(long, matching_opt["short"], argument))

        def parse_short(arg):
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

        while i < len(argv):
            arg = argv[i]
            if arg.startswith("-"):
                if arg.startswith("--"):
                    parse_long(arg)
                else:
                    parse_short(arg)
            elif arg in path[-1].commands:
                cmd.append(arg)
                path.append(path[-1].commands[arg])
            else:
                raise CommandLineError("Unknown command " + arg)
            i += 1

        if path[-1].require_command:
            raise CommandLineError("Missing subcommand")

        return CommandLine(cmd, options)
                    
