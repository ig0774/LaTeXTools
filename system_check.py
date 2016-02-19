from __future__ import print_function

import sublime
import sublime_plugin

import copy
import os
import subprocess
import sys
import textwrap
import threading

from io import StringIO


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
else:
    def expand_vars(texpath):
        return os.path.expandvars(texpath)


def _get_texpath():
    texpath = get_setting(sublime.platform(), {}).get('texpath')
    return expand_vars(texpath) if texpath is not None else None


def get_version_info(executable, path=None):
    startupinfo = None
    shell = False
    if sublime.platform() == 'windows':
        # ensure console window doesn't show
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        shell = True

    env = copy.copy(os.environ)
    if path is not None:
        env['PATH'] = path

    p = subprocess.Popen(
        [executable, '--version'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        startupinfo=startupinfo,
        shell=shell,
        env=env
    )

    stdout, _ = p.communicate()
    return stdout.decode('utf-8').strip().split('\n', 1)[0]


def get_max_width(table, column):
    return max(len(unicode(row[column])) for row in table)


def tabulate(table, wrap_column=80, output=sys.stdout):
    column_widths = [get_max_width(table, i) for i in range(len(table[0]))]
    column_widths = [width if width <= wrap_column else wrap_column
                     for width in column_widths]

    headers = table.pop(0)

    for i in range(len(headers)):
        padding = 2 if i < len(headers) - 1 else 0
        print(headers[i].ljust(column_widths[i] + padding), end=u'',
              file=output)
    print(u'', file=output)

    for i in range(len(headers)):
        padding = 2 if i < len(headers) - 1 else 0
        if headers[i]:
            print((u'-' * len(headers[i])).ljust(column_widths[i] + padding),
                  end=u'', file=output)
        else:
            print(u''.ljust(column_widths[i] + padding), end=u'', file=output)
    print(u'', file=output)

    added_row = False
    for j, row in enumerate(table):
        for i in range(len(row)):
            padding = 2 if i < len(row) - 1 else 0
            column = unicode(row[i])
            if len(column) > 95:
                wrapped = textwrap.wrap(column, 95)
                column = wrapped.pop(0)
                lines = u''.join(wrapped)

                if added_row:
                    table[j + 1][i] = lines
                else:
                    table.insert(j + 1, [u''] * len(row))
                    table[j + 1][i] = lines
                    added_row = True

            print(unicode(column).ljust(column_widths[i] + padding), end=u'',
                  file=output)

        added_row = False
        print(u'', file=output)

    print(u'', file=output)


class SystemCheckThread(threading.Thread):

    def __init__(self, sublime_exe=None, uses_miktex=False, on_done=None):
        super(SystemCheckThread, self).__init__()
        self.sublime_exe = sublime_exe
        self.uses_miktex = uses_miktex
        self.on_done = on_done

    def run(self):
        texpath = _get_texpath() or os.environ['PATH']
        results = []

        table = [
            ['Variable', 'Value']
        ]

        table.append([
            'PATH', texpath
        ])

        results.append(table)

        table = [
            ['Program', 'Location', 'Required', 'Status', '', 'Version']
        ]

        sublime_exe = get_sublime_executable()
        available = sublime_exe is not None
        table.append([
            'sublime',
            sublime_exe,
            u'yes',
            u'available' if available else u'missing',
            u'\u2705' if available else u'\u274c',
            get_version_info(sublime_exe, path=texpath) if available else u''
        ])

        program = 'latexmk' if not self.uses_miktex else 'texify'
        location = which(program, path=texpath)
        available = location is not None
        table.append([
            program,
            location,
            u'yes',
            u'available' if available else u'missing',
            u'\u2705' if available else u'\u274c',
            get_version_info(location, path=texpath) if available else u''
        ])

        for program in ['pdflatex', 'xelatex', 'lualatex', 'biber',
                        'bibtex', 'kpsewhich']:
            location = which(program, path=texpath)
            available = location is not None
            table.append([
                program,
                location,
                u'no',
                u'available' if available else u'missing',
                u'\u2705' if available else u'\u274c',
                get_version_info(location, path=texpath) if available else u''
            ])

        results.append(table)

        if callable(self.on_done):
            self.on_done(results)


class LatextoolsSystemCheckCommand(sublime_plugin.ApplicationCommand):

    def run(self):
        uses_miktex = \
            get_setting(sublime.platform(), {}).get('distro') == 'miktex'

        t = SystemCheckThread(
            uses_miktex=uses_miktex,
            on_done=self.on_done
        )

        t.start()

    def on_done(self, results):
        def _on_done():
            view = sublime.active_window().new_file()
            view.set_scratch(True)
            view.settings().set('word_wrap', False)
            view.set_name('LaTeXTools System Check')
            view.set_encoding('UTF-8')

            buf = StringIO()
            for table in results:
                tabulate(table, output=buf)

            tabulate([[u'Builder'], [get_setting('builder')]], output=buf)

            builder_path = get_setting('builder_path')
            if builder_path:
                tabulate([[u'Builder Path'], [builder_path]], output=buf)

            table = [['Builder Setting', 'Value']]
            builder_settings = get_setting('builder_settings')
            for key in builder_settings:
                table.append([key, builder_settings[key]])
            tabulate(table)

            view.run_command('latextools_append_text',
                             {'text': buf.getvalue()})

            print(buf.getvalue())
            buf.close()

        sublime.set_timeout(_on_done, 0)


class LatextoolsAppendTextCommand(sublime_plugin.TextCommand):

    def run(self, edit, text):
        view = self.view
        view.insert(edit, 0, text)
