import sublime
import os
import sys

import subprocess
from subprocess import Popen, PIPE

try:
    from latextools_utils.settings import get_setting
except ImportError:
    from . import get_setting

if sublime.version() < '3000':
    def expand_vars(texpath):
        return os.path.expandvars(texpath).encode(sys.getfilesystemencoding())

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")
else:
    def expand_vars(texpath):
        return os.path.expandvars(texpath)

    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

__all__ = ['external_command']


def _get_texpath():
    try:
        texpath = get_setting(sublime.platform(), {}).get('texpath')
    except AttributeError:
        # hack to reload this module in case the calling module was reloaded
        exc_info = sys.exc_info
        try:
            reload(sys.modules[_get_texpath.__module__])
            texpath = get_setting('texpath')
        except:
            reraise(*exc_info)

    return expand_vars(texpath) if texpath is not None else None


def external_command(command, cwd=None):
    '''
    Takes a command object to be passed to subprocess.Popen.

    Returns a tuple consisting of
        (return_code, stdout, stderr)
    Raises OSError if command not found
    '''
    texpath = _get_texpath() or os.environ['PATH']
    env = dict(os.environ)
    env['PATH'] = texpath

    # Windows-specific adjustments
    startupinfo = None
    shell = False
    if sublime.platform() == 'windows':
        # ensure console window doesn't show
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        shell = True

    print('Running %s' % (' '.join(command)))
    p = Popen(
        command,
        stdout=PIPE,
        stdin=PIPE,
        stderr=PIPE,
        startupinfo=startupinfo,
        shell=shell,
        env=env,
        cwd=cwd
    )

    stdout, stderr = p.communicate()
    return (
        p.returncode,
        stdout.decode('utf-8').rstrip(),
        stderr.decode('utf-8').rstrip()
    )
