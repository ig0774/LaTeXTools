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

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")
else:
    from imp import reload

    strbase = str

    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

def is_bib_buffer(view, point=0):
    return view.match_selector(point, 'text.bibtex') or is_biblatex_buffer(view, point)

def is_biblatex_buffer(view, point=0):
    return view.match_selector(point, 'text.biblatex')

def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

def get_tex_extensions():
    try:
        tex_file_exts = get_setting('tex_file_exts', ['.tex'])
    except AttributeError:
        # hack to reload this module in case the calling module was reloaded
        exc_info = sys.exc_info
        try:
            reload(sys.modules[get_tex_extensions.__module__])
            tex_file_exts = get_setting('tex_file_exts', ['.tex'])
        except:
            reraise(*exc_info)

    return [s.lower() for s in set(tex_file_exts)]

def is_tex_file(file_name):
    if not isinstance(file_name, strbase):
        raise TypeError('file_name must be a string')

    tex_file_exts = get_tex_extensions()
    for ext in tex_file_exts:
        if file_name.lower().endswith(ext):
            return True
    return False
