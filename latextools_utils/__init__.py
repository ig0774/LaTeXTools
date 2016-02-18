from __future__ import print_function

import os
import sublime
import sys


def get_sublime_exe():
    '''
    Utility function to get the full path to the currently executing
    Sublime instance.
    '''
    plat_settings = get_setting(sublime.platform(), {})
    sublime_executable = plat_settings.get('sublime_executable', None)

    if sublime_executable:
        return sublime_executable

    # we cache the results of the other checks, if possible
    if hasattr(get_sublime_exe, 'result'):
        return get_sublime_exe.result

    # are we on ST3
    if hasattr(sublime, 'executable_path'):
        get_sublime_exe.result = sublime.executable_path()
    # in ST2 the Python executable is actually "sublime_text"
    elif sys.executable != 'python' and os.path.isabs(sys.executable):
        get_sublime_exe.result = sys.executable

    # on osx, the executable does not function the same as subl
    if sublime.platform() == 'osx':
        get_sublime_exe.result = os.path.normpath(
            os.path.join(
                os.path.dirname(get_sublime_exe.result),
                '..',
                'SharedSupport',
                'bin',
                'subl'
            )
        )

    return get_sublime_exe.result

    print(
        'Cannot determine the path to your Sublime installation. Please ' +
        'set the "sublime_executable" setting in your settings.'
    )

    return None


def is_bib_buffer(view, point=0):
    return view.match_selector(point, 'text.bibtex') or is_biblatex_buffer(view, point)


def is_biblatex_buffer(view, point=0):
    return view.match_selector(point, 'text.biblatex')


def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

# ensure the utility modules are available
try:
    from latextools_utils.settings import get_setting
    from latextools_utils.is_tex_file import get_tex_extensions, is_tex_file
    from latextools_utils.tex_directives import parse_tex_directives
    import latextools_utils.analysis
    import latextools_utils.cache
    import latextools_utils.sublime_utils
    import latextools_utils.utils
except ImportError:
    from .settings import get_setting
    from .is_tex_file import get_tex_extensions, is_tex_file
    from .tex_directives import parse_tex_directives
    from . import analysis
    from . import cache
    from . import sublime_utils
    from . import utils
