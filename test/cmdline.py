from studip.cmdline import CommandLineParser, CommandLineError
from unittest import TestCase


class CommandLineTest(TestCase):
    def test_build_parser(self):
        p = CommandLineParser()
        foo = p.command("foo")
        bar = foo.command("bar")
        p.option("aa", "a", False, "AA")
        foo.option(None, "b", False, "BB")
        bar.option("cc", None, True, "CC")

        with self.assertRaises(ValueError):
            p.command(None)
        with self.assertRaises(ValueError):
            p.command("foo") # Already defined

        with self.assertRaises(ValueError):
            p.option(None, None, False, "")
        with self.assertRaises(ValueError):
            p.option("foo", "foo", False, "")

    def test_parse_commands(self):
        p = CommandLineParser(require_command=True)
        foo = p.command("foo")
        bar = p.command("bar", require_subcommand=True)
        f1 = foo.command("f1")
        ff1 = f1.command("ff1")
        f2 = foo.command("f2")
        b1 = bar.command("b1")
        b2 = bar.command("b2")
        baz = p.command("baz")

        q = p.parse(["ex", "foo"])
        self.assertEqual(q.command, ["foo"])
        q = p.parse(["ex", "foo", "f1"])
        self.assertEqual(q.command, ["foo", "f1"])
        q = p.parse(["ex", "foo", "f1", "ff1"])
        self.assertEqual(q.command, ["foo", "f1", "ff1"])
        q = p.parse(["ex", "foo", "f2"])
        self.assertEqual(q.command, ["foo", "f2"])
        q = p.parse(["ex", "bar", "b1"])
        self.assertEqual(q.command, ["bar", "b1"])
        q = p.parse(["ex", "bar", "b2"])
        self.assertEqual(q.command, ["bar", "b2"])
        q = p.parse(["ex", "baz"])
        self.assertEqual(q.command, ["baz"])

        with self.assertRaises(CommandLineError):
            p.parse([])
        with self.assertRaises(CommandLineError):
            p.parse(["ex"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "abc"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "foo", "foo"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "f1"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "f1", "foo"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "foo", "f1", "ff1", "ff1"])
        with self.assertRaises(CommandLineError):
            p.parse(["ex", "bar"])


