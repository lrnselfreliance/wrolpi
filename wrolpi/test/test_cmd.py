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


async def test_run_command_start_new_session_reaps_children(test_directory):
    """Children left behind by the command are killed with its process group.

    single-file does not close the browser it spawns; the process group kill reaps it."""
    script = test_directory / 'leaky.sh'
    # The grandchild sleeps long after the script exits.
    script.write_text('#!/bin/sh\nsleep 60 &\necho $! > leaked.pid\n')

    result = await cmd.run_command(('sh', 'leaky.sh'), cwd=test_directory, timeout=10, start_new_session=True)

    assert result.return_code == 0
    leaked_pid = int((test_directory / 'leaked.pid').read_text().strip())
    # The kill is delivered asynchronously; the killed process may linger as a zombie briefly.
    for _ in range(20):
        if not cmd.pid_is_running(leaked_pid):
            break
        await asyncio.sleep(0.1)
    assert not cmd.pid_is_running(leaked_pid), 'The leaked child should have been killed with the process group'

    # Without start_new_session the child survives (and must be cleaned up by the test).
    result = await cmd.run_command(('sh', 'leaky.sh'), cwd=test_directory, timeout=10)
    assert result.return_code == 0
    leaked_pid = int((test_directory / 'leaked.pid').read_text().strip())
    assert cmd.pid_is_running(leaked_pid)
    os.kill(leaked_pid, 9)


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


STREAMING_SCRIPT = '''#!/bin/sh
echo "line one"
echo "line two"
echo "line three"
echo stderr >&2
'''


async def test_run_command_streaming(test_directory):
    """run_command_streaming captures stdout line-by-line and calls callback."""
    (test_directory / 'stream.sh').write_text(STREAMING_SCRIPT)
    lines = []
    result = await cmd.run_command(
        ('sh', 'stream.sh'),
        cwd=test_directory,
        stdout_callback=lambda line: lines.append(line),
    )
    assert result.return_code == 0
    assert result.cancelled is False
    assert result.stdout == b'line one\nline two\nline three\n'
    assert result.stderr == b'stderr\n'
    assert lines == ['line one', 'line two', 'line three']


async def test_run_command_streaming_no_callback(test_directory):
    """run_command_streaming works without a callback."""
    (test_directory / 'stream.sh').write_text(STREAMING_SCRIPT)
    result = await cmd.run_command(('sh', 'stream.sh'), cwd=test_directory)
    assert result.return_code == 0
    assert result.stdout == b'line one\nline two\nline three\n'
    assert result.stderr == b'stderr\n'


async def test_run_command_streaming_timeout(test_directory):
    """Timeout is obeyed for streaming."""
    result = await cmd.run_command(('sleep', '10'), timeout=2)
    assert result.return_code == -9
    assert result.cancelled is False
    assert result.elapsed >= 2
