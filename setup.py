#!/usr/bin/env python3

import re, os
from setuptools import setup

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    with open("studip/__init__.py", "r") as file:
        version = re.search('^__version__\s*=\s*"(.*)"', file.read(), re.M).group(1)

    with open("README", "rb") as f:
        long_descr = f.read().decode("utf-8")

    setup(
        name = "studip-client",
        packages = ["studip"],
        entry_points = {
            "console_scripts": [ "studip = studip.application:main" ]
        },
        include_package_data = True,
        install_requires = [
            "requests",
            "appdirs"
        ],
        version = version,
        description = "CLI Client for the Stud.IP University Access Portal",
        long_description = long_descr,
        author = "Fabian Knorr",
        url = "https://github.com/fknorr/studip-client"
    )
