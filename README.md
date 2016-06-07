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

Configuration
-------------

At the moment, the only way to modify _studip-client_'s configuration is by editing
`<sync-dir>/.studip/studip.conf`. It is divided into three sections:

- `server`: The studip server's base URLs. The only web interface the client has been tested
  against is `uni-passau.de`, so changing these settings to connect to other servers will probably
  not work correctly.
- `filesystem`: Specifies how files will be saved to disk.
    - `path_format`: A string specifying how each file's path will be built from its metadata. The
      following placeholders are available:

      ```
      {semester}        Course semester
      {course-id}       Course hash-id
      {course}          Course name
      {type}            Course type (e.g. "Lecture")
      {path}            Path of the file's containing directory
      {short-path}      Like {path}, but with "Allgemeiner Dateiordner" removed
      {id}              File hash-id
      {name}            Original file name, without extension
      {ext}             File extension (e.g. "pdf")
      {description}     Full file description
      {descr-no-ext}    Like {description}, but with the file extension stripped (if any)
      {author}          File author's name
      {time}            Time of creation
      ```

- `user`: Login credentials. The password will be encrypted with `~/.cache/studip/secret` as the
  key, which means it cannot be edited directly.

Security
--------

_studip-client_ works by crawling the Stud.IP web interface and will therefore ask for your
username and password. The credentials are stored locally in `<sync-dir>/.studip/studip.conf` and
encrypted with a machine-local auto-generated key found in `~/.cache/studip/secret` so that
simply obtaining a copy of your config file is not enough to recover your password.

All connections to the university servers transporting the login data are made via HTTPS.
Your credentials will not be copied or distributed in any other way.

If you're interested in verifying this claim manually, the relevant source code can be found in
`studip/application.py`, `Application.open_session()`.
