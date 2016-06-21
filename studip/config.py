import ast

from configparser import ConfigParser
from errno import ENOENT


class Config:
    def __init__(self, file_name, defaults={}):
        self.file_name = file_name
        self.cp = ConfigParser()

        for (cat, key), value in defaults.items():
            self[cat, key] = value

        try:
            with open(self.file_name, "r", encoding="utf-8") as file:
                self.cp.read_file(file)
        except Exception as e:
            if not (isinstance(e, IOError) and e.errno == ENOENT):
                self.print_io_error("Unable to read configuration from", self.file_name, e)
                sys.stderr.write("Starting over with a fresh configuration\n")

    def __enter__(self):
        pass

    def __exit__(self, x, y, z):
        self.write()

    def write(self):
        try:
            with open(self.file_name, "w", encoding="utf-8") as file:
                self.cp.write(file)
        except Exception as e:
            self.print_io_error("Unable to write to", self.file_name, e)
            raise

    def __getitem__(self, path):
        cat, key = path
        repr = self.cp[cat][key]
        try:
            return ast.literal_eval(repr)
        except SyntaxError:
            return repr

    def __setitem__(self, path, value):
        cat, key = path
        if not cat in self.cp:
            self.cp[cat] = {}
        self.cp[cat][key] = repr(value)

    def __delitem__(self, path):
        cat, key = path
        del self.cp[cat][key]

    def __contains__(self, path):
        cat, key = path
        return cat in self.cp and key in self.cp[cat]
