from __future__ import print_function

try:
    from latextools_utils.is_tex_file import get_tex_extensions, is_tex_file
except ImportError:
    from .is_tex_file import get_tex_extensions, is_tex_file

try:
    from latextools_utils.settings import get_setting
except ImportError:
    from .settings import get_setting


def is_bib_buffer(view, point=0):
    return view.match_selector(point, 'text.bibtex') or is_biblatex_buffer(view, point)

def is_biblatex_buffer(view, point=0):
    return view.match_selector(point, 'text.biblatex')

def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

import sublime

# ensure the utility modules are available
if sublime.version() < '3000':
    import latextools_utils.analysis
    import latextools_utils.cache
    import latextools_utils.utils
