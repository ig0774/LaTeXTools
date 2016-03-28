from __future__ import print_function


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
    import latextools_utils.external_command
    import latextools_utils.sublime_utils
    import latextools_utils.utils
except ImportError:
    from .settings import get_setting
    from .is_tex_file import get_tex_extensions, is_tex_file
    from .tex_directives import parse_tex_directives
    from . import analysis
    from . import cache
    from . import external_command
    from . import sublime_utils
    from . import utils
