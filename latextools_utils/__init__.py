from __future__ import print_function


def is_bib_buffer(view, point=0):
    return (
        view.score_selector(point, 'text.bibtex') > 0 or
        is_biblatex_buffer(view, point)
    )


def is_biblatex_buffer(view, point=0):
    return view.score_selector(point, 'text.biblatex') > 0


def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.score_selector(point, 'text.tex.latex') > 0

try:
    from latextools_utils.settings import get_setting
except ImportError:
    from .settings import get_setting
