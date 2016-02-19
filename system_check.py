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
    from latextools_plugin import (
        add_plugin_path, get_plugin, NoSuchPluginException,
        _classname_to_internal_name
    )
    from latextools_utils import get_setting
    from latextools_utils.system import which
    from latextools_utils.tex_directives import parse_tex_directives
    from latextools_utils.sublime_utils import get_sublime_exe
    from jumpToPDF import DEFAULT_VIEWERS
    from getTeXRoot import get_tex_root
except ImportError:
    from .latextools_plugin import (
        add_plugin_path, get_plugin, NoSuchPluginException,
        _classname_to_internal_name
    )
    from .latextools_utils import get_setting
    from .latextools_utils.system import which
    from .latextools_utils.tex_directives import parse_tex_directives
    from .latextools_utils.sublime_utils import get_sublime_exe
    from .jumpToPDF import DEFAULT_VIEWERS
    from .getTeXRoot import get_tex_root

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
        old.update(dict(
            (k.encode(sys.getfilesystemencoding()), v)
            for (k, v) in new.items()
        ))

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")


def _get_texpath(view):
    texpath = get_setting(sublime.platform(), {}, view).get('texpath')
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
        if sublime.platform() != 'windows':
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
            output.write(
                (u'-' * len(headers[i])).ljust(column_widths[i] + padding)
            )
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
            ['Program', 'Location', 'Status', 'Version']
        ]

        # skip sublime_exe on OS X
        # we only use this for the hack to re-focus on ST
        # which doesn't work on OS X anyway
        if sublime.platform() != 'osx':
            sublime_exe = self.sublime_exe
            available = sublime_exe is not None

            if available:
                if not os.path.isabs(sublime_exe):
                    sublime_exe = which(sublime_exe)

                basename, extension = os.path.splitext(sublime_exe)
                if extension is not None:
                    sublime_exe = ''.join((basename, extension.lower()))

            version_info = get_version_info(
                sublime_exe, env=env
            ) if available else None

            table.append([
                'sublime',
                sublime_exe,
                u'available' if available and version_info is not None else u'missing',
                version_info if version_info is not None else u'unavailable'
            ])

        for program in ['latexmk' if not self.uses_miktex else 'texify',
                        'pdflatex', 'xelatex', 'lualatex', 'biber',
                        'bibtex', 'bibtex8', 'kpsewhich']:
            location = which(program, path=texpath)
            available = location is not None

            if available:
                basename, extension = os.path.splitext(location)
                if extension is not None:
                    location = ''.join((basename, extension.lower()))

            version_info = get_version_info(
                location, env=env
            ) if available else None

            table.append([
                program,
                location,
                u'available' if available and version_info is not None else u'missing',
                version_info if version_info is not None else u'unavailable'
            ])

        results.append(table)

        if callable(self.on_done):
            self.on_done(results)


class LatextoolsSystemCheckCommand(sublime_plugin.ApplicationCommand):

    def run(self):
        uses_miktex = \
            get_setting(sublime.platform(), {}).get('distro') == 'miktex'

        self.view = sublime.active_window().active_view()

        t = SystemCheckThread(
            sublime_exe=get_sublime_exe(),
            uses_miktex=uses_miktex,
            texpath=_get_texpath(self.view) or os.environ['PATH'],
            build_env=get_setting('builder_settings', {}).get(
                sublime.platform(), {}
            ).get('env'),
            on_done=self.on_done
        )

        t.start()

    def on_done(self, results):
        def _on_done():
            buf = StringIO()
            for item in results:
                tabulate(item, output=buf)

            builder_name = get_setting(
                'builder', 'traditional', view=self.view
            )

            if builder_name in ['', 'default']:
                builder_name = 'traditional'

            builder_settings = get_setting('builder_settings', view=self.view)
            builder_path = get_setting('builder_path', view=self.view)

            if builder_name in ['simple', 'traditional', 'script']:
                builder_path = None
            else:
                bld_path = os.path.join(sublime.packages_path(), builder_path)
                add_plugin_path(bld_path)

            builder_name = _classname_to_internal_name(builder_name)

            try:
                get_plugin('{0}_builder'.format(builder_name))
                builder_available = True
            except NoSuchPluginException:
                traceback.print_exc()
                builder_available = False

            tabulate([
                [u'Builder', u'Status'],
                [
                    builder_name,
                    u'available' if builder_available else u'missing'
                ]
            ],
                output=buf)

            if builder_path:
                tabulate([[u'Builder Path'], [builder_path]], output=buf)

            if builder_settings is not None:
                table = [[u'Builder Setting', u'Value']]
                for key in sorted(builder_settings.keys()):
                    value = builder_settings[key]
                    table.append([key, value])
                tabulate(table, output=buf)

            # is current view a TeX file?
            view = self.view
            if view.score_selector(0, 'text.tex.latex') != 0:
                tex_root = get_tex_root(view)
                tex_directives = parse_tex_directives(
                    tex_root,
                    multi_values=['options'],
                    key_maps={'ts-program': 'program'}
                )

                tabulate([[u'TeX Root'], [tex_root]], output=buf)

                tabulate([
                    [u'LaTeX Engine'],
                    [
                        tex_directives.get(
                            'program',
                            get_setting(
                                'program', 'pdflatex', self.view
                            )
                        )
                    ]
                ], output=buf)

                options = get_setting('builder_settings', {}, self.view).\
                    get('options', [])
                options.extend(tex_directives.get('options', []))

                if len(options) > 0:
                    table = [[u'LaTeX Options']]
                    for option in options:
                        table.append([option])

                    tabulate(table, output=buf)

            default_viewer = DEFAULT_VIEWERS.get(sublime.platform(), None)
            viewer_name = get_setting('viewer', default_viewer)
            if viewer_name in ['', 'default']:
                viewer_name = default_viewer

            try:
                get_plugin(viewer_name + '_viewer')
                viewer_available = True
            except NoSuchPluginException:
                viewer_available = False

            tabulate([
                [u'Viewer', u'Status'],
                [
                    viewer_name,
                    u'available' if viewer_available else u'missing'
                ]
            ],
                output=buf)

            new_view = sublime.active_window().new_file()
            new_view.set_scratch(True)
            new_view.settings().set('word_wrap', False)
            new_view.set_name('LaTeXTools System Check')
            if sublime.version() < '3103':
                new_view.settings().set(
                    'syntax',
                    'Packages/LaTeXTools/system_check.hidden-tmLanguage'
                )
            else:
                new_view.settings().set(
                    'syntax', 'Packages/LaTeXTools/system_check.sublime-syntax'
                )

            new_view.set_encoding('UTF-8')

            new_view.run_command(
                'latextools_insert_text',
                {'text': buf.getvalue()}
            )

            new_view.set_read_only(True)

            buf.close()

        sublime.set_timeout(_on_done, 0)


class LatextoolsInsertTextCommand(sublime_plugin.TextCommand):

    def run(self, edit, text):
        view = self.view
        view.insert(edit, 0, text)
