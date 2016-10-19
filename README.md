Stud.IP Client
==============

_studip-client_ is a CLI application for synchronizing the directory tree from a Stud.IP
university account to the local file system.

It does this by creating a local database of course files, downloading them into its repository
and presenting them in the file system as one or several different _views_.

_studip-client_ is currently only implemented for the University of Passau (https://uni-passau.de/).

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
$ studip <operation> [-d directory]
```

The most important operations are

- `help`: Display a list of operations and options.
- `update`: Update the local course and file database from Stud.IP.
- `fetch`: Download all unknown remote files to the local repository
- `checkout`: Update all views to include newly fetched files
- `sync`: Do an `update` followed by `fetch` and `checkout`.

If no directory is given, the most recently used one is assumed, if _studip-client_ has not been
run before, the directory is read from the standard input.

Configuration
-------------

At the moment, the only way to modify _studip-client_'s configuration is by editing
`<sync-dir>/.studip/studip.conf`. It is divided into three sections:

- `server`: The studip server's base URLs. The only web interface the client has been tested
  against is `uni-passau.de`, so changing these settings to connect to other servers will probably
  not work correctly.

- `connection`: Controls how _studip-client_ connects to the Stud.IP servers. The `concurrency`
  settings controls the maximum number of simultaneous requests.

- `user`: Login credentials. The password will be encrypted with `~/.cache/studip/secret` as the
  key, which means it cannot be edited directly.

Views
-----

How files are checked out into the sync directory is controlled by _views_. Each view consists of
a directory tree containing hard-links to the original files in `.studip/files/`. The following
operations are available to show and modify views:

- `view show`: Lists all available views.
- `view show <name>`: Shows details about a specific view
- `view add <name> [<key> <value>...]`: Adds a new view, setting the attributes `key = value`
- `view rm <name>`: Removes a view and the associated directory structure
- `view reset-deleted <name>`: Forget about deleted files, allowing them to be checked out again
- `view reset-deleted`: As above, but for all views.

When _studip-client_ is first invoked, a default view will be created. If you want to change
the directory structure, you first need to remove it - If multiple views are to be created, they
need to reside in subdirectories, which the default view does not.

For example:

```
$ studip view rm default
$ studip view add my_view base my_subdir charset ascii
```

The `rm` operation removes the directory tree, but keeps any files that weren't created by
_studip-client_. This works even if managed files have been renamed by the user.

Here, when creating the new view, the `base` attribute is set to `my_subdir` and the charset to
ASCII. The following attributes are available:

- `format`: A string specifying how each file's path will be built from its metadata. The
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

- `base`: The base directory containing the view's directory tree. If there is only one view,
    this may be empty. If there are multiple views, each one needs its own subdirectory.

- `charset`: The class of allowed characters in a file or folder name. Characters which are not
    in this class are substituted or removed.

    ```
    unicode           All unicode characters except / and : are permitted
    ascii             Only ASCII (<= 0x7f) characters are preserved
    identifier        All characters but [A-Za-z0-9_] are removed
    ```

- `escape`: Specifies how the path should be encoded to remove invalid characters.

    ```
    similar           Replace : and / with similar looking characters
    typeable          Like <similar>, but only uses characters found on a common keyboard
    camel             FilesAndFolders/AreTransformedToCamelCase/WhileRemoving.punctuation
    snake             special_chars/are_replaced_by_underscores/characters_are.lowercase
    ```

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
