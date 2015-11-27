import sublime
import os
import sys

import subprocess
from subprocess import Popen, PIPE

try:
    from latextools_settings import get_setting    
except ImportError:
    from ..latextools_settings import get_setting

if sublime.version() < '3000':
    def expand_vars(texpath):
        return os.path.expandvars(texpath).encode(sys.getfilesystemencoding())
else:
    def expand_vars(texpath):
        return os.path.expandvars(texpath)

__all__ = ['external_command']

def _get_texpath():
    texpath = get_setting(sublime.platform(), {}).get('texpath')
    if texpath is None:
        texpath = get_setting('texpath')

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
