from __future__ import print_function

from collections import Mapping
import sublime
import sys

try:
    from latextools_settings import get_setting
except ImportError:
    from ..latextools_settings import get_setting

if sys.version_info < (3, 0):
    strbase = basestring
else:
    strbase = str

def is_bib_buffer(view, point=0):
    return view.match_selector(point, 'text.bibtex') or is_biblatex_buffer(view, point)

def is_biblatex_buffer(view, point=0):
    return view.match_selector(point, 'text.biblatex')

def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

def get_tex_extensions():
    tex_file_exts = get_setting('tex_file_exts', ['.tex'])
    return [s.lower() for s in set(tex_file_exts)]

def is_tex_file(file_name):
    if not isinstance(file_name, strbase):
        raise TypeError('file_name must be a string')

    tex_file_exts = get_tex_extensions()
    for ext in tex_file_exts:
        if file_name.lower().endswith(ext):
            return True
    return False
