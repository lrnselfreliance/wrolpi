import os
from pathlib import Path

from wrolpi import cmd
from wrolpi.test.common import skip_circleci


def test_which(test_directory):
    # Default location in Debian Linux.
    assert cmd.which('ls') == Path('/usr/bin/ls')
    # This executable does not exist.
    assert cmd.which('asdf') is None
    # The alternative path does not exist either.
    assert cmd.which('asdf', 'asdf') is None
    # Directories are ignored.
    assert cmd.which('asdf', '/tmp') is None

    # Create an executable.
    foo = test_directory / 'foo'
    foo.touch()
    assert cmd.which('asdf', str(foo)) is None
    os.chmod(foo, 0o777)
    assert cmd.which('asdf', str(foo)) == foo


@skip_circleci
def test_which_chromium():
    # Multiple names can be tried.
    assert cmd.which('chromium-browser', 'chromium') == Path('/usr/bin/chromium')
