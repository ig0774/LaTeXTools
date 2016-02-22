from __future__ import print_function

import sublime
import sublime_plugin

import copy
import os
import re
import signal
import subprocess
import sys
import textwrap
import threading
import traceback

try:
    from io import StringIO
except ImportError:
    # support ST2 on Linux
    from StringIO import StringIO

try:
    from latextools_utils import get_setting
    from latextools_utils.system import which
    from jumpToPDF import get_sublime_executable
except ImportError:
    from .latextools_utils import get_setting
    from .latextools_utils.system import which
    from .jumpToPDF import get_sublime_executable

if sys.version_info >= (3,):
    unicode = str

    def expand_vars(texpath):
        return os.path.expandvars(texpath)

    def update_environment(old, new):
        old.update(new.items())

    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
else:
    def expand_vars(texpath):
        return os.path.expandvars(texpath).encode(sys.getfilesystemencoding())

    def update_environment(old, new):
        old.update((dict((k.encode(sys.getfilesystemencoding()), v) for (k, v) in new.items())))

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")


def _get_texpath():
    texpath = get_setting(sublime.platform(), {}).get('texpath')
    return expand_vars(texpath) if texpath is not None else None


class SubprocessTimeoutThread(threading.Thread):

    def __init__(self, timeout, *args, **kwargs):
        super(SubprocessTimeoutThread, self).__init__()
        self.args = args
        self.kwargs = kwargs
        # ignore the preexec_fn if specified
        if 'preexec_fn' in kwargs:
            del self.kwargs['preexec_fn']

        self.timeout = timeout

        self.returncode = None
        self.stdout = None
        self.stderr = None

    def run(self):
        if sublime.platform != 'windows':
            preexec_fn = os.setsid
        else:
            preexec_fn = None

        try:
            self._p = p = subprocess.Popen(
                *self.args,
                preexec_fn=preexec_fn,
                **self.kwargs
            )

            self.stdout, self.stderr = p.communicate()
            self.returncode = p.returncode
        except Exception as e:
            # just in case...
            self.kill_process()
            reraise(e)

    def start(self):
        super(SubprocessTimeoutThread, self).start()
        self.join(self.timeout)

        # if the timeout occurred, kill the entire process chain
        if self.isAlive():
            self.kill_process()

    def kill_process(self):
        try:
            if sublime.platform == 'windows':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                subprocess.call(
                    'taskkill /t /f /pid {pid}'.format(pid=self._p.pid),
                    startupinfo=startupinfo,
                    shell=True
                )
            else:
                os.killpg(self._p.pid, signal.SIGKILL)
        except:
            traceback.print_exc()


def get_version_info(executable, env=None):
    print('Checking {0}...'.format(executable))
    startupinfo = None
    shell = False
    if sublime.platform() == 'windows':
        # ensure console window doesn't show
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        shell = True

    if env is None:
        env = os.environ

    try:
        t = SubprocessTimeoutThread(
            30,  # wait 30 seconds
            [executable, '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            shell=shell,
            env=env
        )

        t.start()

        stdout = t.stdout
        if stdout is None:
            return None

        return re.split(r'\r?\n', stdout.decode('utf-8').strip(), 1)[0]
    except:
        return None


def get_max_width(table, column):
    return max(len(unicode(row[column])) for row in table)


def tabulate(table, wrap_column=0, output=sys.stdout):
    column_widths = [get_max_width(table, i) for i in range(len(table[0]))]
    if wrap_column is not None and wrap_column != 0:
        column_widths = [width if width <= wrap_column else wrap_column
                         for width in column_widths]

    headers = table.pop(0)

    for i in range(len(headers)):
        padding = 2 if i < len(headers) - 1 else 0
        output.write(unicode(headers[i]).ljust(column_widths[i] + padding))
    output.write(u'\n')

    for i in range(len(headers)):
        padding = 2 if i < len(headers) - 1 else 0
        if headers[i]:
            output.write((u'-' * len(headers[i])).ljust(column_widths[i] + padding))
        else:
            output.write(u''.ljust(column_widths[i] + padding))
    output.write(u'\n')

    added_row = False
    for j, row in enumerate(table):
        for i in range(len(row)):
            padding = 2 if i < len(row) - 1 else 0
            column = unicode(row[i])
            if wrap_column is not None and wrap_column != 0 and \
                    len(column) > wrap_column:
                wrapped = textwrap.wrap(column, wrap_column)
                column = wrapped.pop(0)
                lines = u''.join(wrapped)

                if added_row:
                    table[j + 1][i] = lines
                else:
                    table.insert(j + 1, [u''] * len(row))
                    table[j + 1][i] = lines
                    added_row = True

            output.write(column.ljust(column_widths[i] + padding))

        added_row = False
        output.write(u'\n')
    output.write(u'\n')


class SystemCheckThread(threading.Thread):

    def __init__(self, sublime_exe=None, uses_miktex=False, texpath=None,
                 build_env=None, on_done=None):
        super(SystemCheckThread, self).__init__()
        self.sublime_exe = sublime_exe
        self.uses_miktex = uses_miktex
        self.texpath = texpath
        self.build_env = build_env
        self.on_done = on_done

    def run(self):
        texpath = self.texpath
        results = []

        env = copy.deepcopy(os.environ)

        if self.texpath is not None:
            env['PATH'] = self.texpath
        if self.build_env is not None:
            update_environment(env, self.build_env)

        table = [
            ['Variable', 'Value']
        ]

        for var in ['PATH', 'TEXINPUTS', 'BSTINPUTS']:
            table.append([var, env.get(var, '')])

        if self.uses_miktex:
            for var in ['BIBTEX', 'LATEX', 'PDFLATEX', 'MAKEINDEX',
                        'MAKEINFO', 'TEX', 'PDFTEX', 'TEXINDEX']:
                value = env.get(var, None)
                if value is not None:
                    table.append([var, value])

        results.append(table)

        table = [
            ['Program', 'Location', 'Status', '', 'Version']
        ]

        # skip sublime_exe on OS X
        # we only use this for the hack to re-focus on ST
        # which doesn't work on OS X anyway
        if sublime.platform() != 'osx':
            sublime_exe = self.sublime_exe
            available = sublime_exe is not None
            version_info = get_version_info(sublime_exe, env=env) if available else None
            table.append([
                'sublime',
                sublime_exe,
                u'available' if available and version_info is not None else u'missing',
                u'\u2705' if available and version_info is not None else u'\u274c',
                version_info if version_info is not None else u'unavailable'
            ])

        for program in ['latexmk' if not self.uses_miktex else 'texify',
                        'pdflatex', 'xelatex', 'lualatex', 'biber',
                        'bibtex', 'kpsewhich']:
            location = which(program, path=texpath)
            available = location is not None
            version_info = get_version_info(location, env=env) if available else None
            table.append([
                program,
                location,
                u'available' if available and version_info is not None else u'missing',
                u'\u2705' if available and version_info is not None else u'\u274c',
                version_info if version_info is not None else u'unavailable'
            ])

        results.append(table)

        if callable(self.on_done):
            self.on_done(results)


class LatextoolsSystemCheckCommand(sublime_plugin.ApplicationCommand):

    def run(self):
        uses_miktex = \
            get_setting(sublime.platform(), {}).get('distro') == 'miktex'

        t = SystemCheckThread(
            sublime_exe=get_sublime_executable(),
            uses_miktex=uses_miktex,
            texpath=_get_texpath() or os.environ['PATH'],
            build_env=get_setting('builder_settings', {})
                        .get(sublime.platform(), {}).get('env'),
            on_done=self.on_done
        )

        t.start()

    def on_done(self, results):
        def _on_done():
            buf = StringIO()
            for item in results:
                tabulate(item, output=buf)

            builder_name = get_setting('builder', 'traditional')
            builder_settings = get_setting('builder_settings')
            builder_path = get_setting('builder_path')
            builder_file_name = builder_name + 'Builder.py'

            if builder_name in ['simple', 'traditional', 'script', 'default', '']:
                builder_path = None
            else:
                builder_path = os.path.join(sublime.packages_path(), builder_path)

            # get the actual builder
            ltt_path = os.path.join(sublime.packages_path(),
                                    'LaTeXTools', 'builders')

            if builder_path:
                bld_path = os.path.join(sublime.packages_path(), builder_path)
            else:
                bld_path = ltt_path
            bld_file = os.path.join(bld_path, builder_file_name)

            builder_available = os.path.isfile(bld_file)

            tabulate([
                [u'Builder', u'Status', u''],
                [
                    builder_name,
                    u'available' if builder_available else u'missing',
                    u'\u2705' if builder_available else u'\u274c'
                ]
            ],
                output=buf)

            if builder_path:
                tabulate([[u'Builder Path'], [builder_path]], output=buf)

            if builder_settings is not None:
                table = [[u'Builder Setting', u'Value']]
                # this is a bit hackish, but appears necessary for things
                # to work on ST2
                for key in sorted(builder_settings._values.keys()):
                    value = builder_settings._values[key]
                    # get the actual values from a SettingsWrapper
                    if hasattr(value, '_values'):
                        value = value._values
                    table.append([key, value])
                tabulate(table, output=buf)

            view = sublime.active_window().new_file()
            view.set_scratch(True)
            view.settings().set('word_wrap', False)
            view.set_name('LaTeXTools System Check')
            view.set_encoding('UTF-8')

            view.run_command('latextools_insert_text',
                             {'text': buf.getvalue()})

            view.set_read_only(True)

            buf.close()

        sublime.set_timeout(_on_done, 0)


class LatextoolsInsertTextCommand(sublime_plugin.TextCommand):

    def run(self, edit, text):
        view = self.view
        view.insert(edit, 0, text)
