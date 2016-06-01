Stud.IP Client
==============

_studip-client_ is a CLI application for synchronizing the directory tree from a Stud.IP
university account to the local file system.

It is currently only implemented for the University of Passau (https://uni-passau.de/).

Installation
------------

Make sure you have at least Python 3.4 installed. There are two ways to use _studip-client_:

### Install system-wide

To install the application for all users, run

```
sudo ./setup.py install
```

This requires `setuptools` to be available. The setup script will
automatically install all prerequisites and add the `studip` executable to `$PATH`.

Then you can simply do

```
$ studip <operation>
```

### Run from source directory

To run _studip-client_ locally, install all dependencies via

```
$ pip3 install requests
$ pip3 install appdirs
```

or a similar command to your package manager. Afterwards, you can run

```
$ ./studip.py <operation>
```

Usage
-----

Usually all you'll ever need is

```
$ studip sync
```

which will connect to Stud.IP, update the local database and fetch all files not yet present
locally.

The general synopsis of _studip-client_ is

```
$ studip <operation> [directory]
```

The most important operations are

- `help`: Display a list of operations and options.
- `update`: Update the local course and file database from Stud.IP.
- `download`: Download files that do not exist yet in the local file system tree.
- `sync`: Do an `update` followed by `download`.

If no directory is given, the most recently used one is assumed, if _studip-client_ has not been
run before, the directory is read from the standard input.

Security
--------

_studip-client_ works by crawling the Stud.IP web interface and will therefore ask for your
user name and password. The credentials are stored locally in `<sync-dir>/.studip/studip.conf` and
sent to the university server via HTTPS. They will not be copied or distributed in any other way.

If you're interested in verifying this claim manually, the relevant source code can be found in
`studip/application.py`, `Application.open_session()`.
