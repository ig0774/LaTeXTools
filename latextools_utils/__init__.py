from __future__ import print_function

def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

try:
	from latextools_utils.settings import get_setting
except ImportError:
	from .settings import get_setting
