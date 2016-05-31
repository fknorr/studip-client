Stud.IP Client
==============

_studip-client_ is a CLI application for synchronizing the directory tree from a Stud.IP
university account to the local file system.

It is currently only implemented for the University of Passau (https://uni-passau.de/).

Installation
------------

Make sure you have at least Python 3.4 installed. There are two ways to use _studip-client_:

### Install system-wide

Use `sudo ./setup.py`. This requires `setuptools` to be available. The setup script will
automatically install all prerequisites and add the `studip` executable to `$PATH`.

Then you can simply do

```
$ studip <operation>
```

### Run from source directory

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

