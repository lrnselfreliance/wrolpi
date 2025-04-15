import asyncio
import os
from pathlib import Path

from wrolpi import cmd


def test_which(test_directory):
    if os.uname()[0] == "Darwin":
        assert cmd.which('ls') == Path('/bin/ls')
    else:
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


TEST_SCRIPT = '''#!/bin/sh
echo stdout
echo stderr >&2
'''


async def test_run_command(test_directory):
    """Can read both stdin and stderr.  Can get return code."""
    (test_directory / 'script.sh').write_text(TEST_SCRIPT)
    result = await cmd.run_command(('sh', 'script.sh'), cwd=test_directory)
    assert result.return_code == 0
    assert result.cancelled is False
    assert result.stdout == b'stdout\n'
    assert result.stderr == b'stderr\n'
    assert result.elapsed == 0


async def test_run_command_timeout(test_directory):
    """Timeout is obeyed."""
    result = await cmd.run_command(('sleep', '10'), timeout=2)
    assert result.return_code == -9
    assert result.cancelled is False
    assert result.stdout == b''
    assert result.stderr == b''
    assert result.elapsed >= 2


async def test_run_command_cancel(test_directory):
    """Run a command, cancel it and test that it was cancelled."""
    task = asyncio.create_task(cmd.run_command(('sleep', '10')))
    try:
        await asyncio.wait_for(task, timeout=1.1)
    except TimeoutError:
        task.cancel()

    result = await task
    assert result.return_code == -9
    assert result.cancelled is True
    assert result.stdout == b''
    assert result.stderr == b''
    assert result.elapsed == 1
