Stud.IP Client
==============

_CLI Client for the Stud.IP University Access Portal_

Installation
------------

Make sure you have at least Python 3.5 installed. There are two ways to use _studip-client_:

1. Use `sudo ./setup.py`. This requires `setuptools` to be available. The setup script will
    automatically install all prerequisites and add the `studip` executable to `$PATH`.

    Then you can simply do

    ```
    $ studip sync
    ```

2. Install all dependencies via

    ```
    pip install requests
    pip install appdirs
    ```

    or a similar command to your package manager. Afterwards, you can run

    ```
    $ ./studip.py sync
    ```

