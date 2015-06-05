import sublime
import os
import sys

import subprocess
from subprocess import Popen, PIPE

if sublime.version() < '3000':
    def expand_vars(texpath):
        return os.path.expandvars(texpath).encode(sys.getfilesystemencoding())
else:
    def expand_vars(texpath):
        return os.path.expandvars(texpath)

__all__ = ['external_command']

def _get_texpath():
    def _get_texpath_setting(settings):
        platform_settings = settings.get(sublime.platform(), {})
        if 'texpath' in platform_settings:
            texpath = platform_settings['texpath']
            if texpath:
                return texpath
        return settings.get('texpath', '')

    texpath = _get_texpath_setting(
        sublime.active_window().active_view().settings()
    ) or _get_texpath_setting(
        sublime.load_settings('LaTeXTools.sublime-settings')
    )

    if texpath:
        return expand_vars(texpath)
    else:
        return ''

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
