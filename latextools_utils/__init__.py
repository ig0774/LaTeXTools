import sublime
import sys

if sys.version_info < (3, 0):
    strbase = basestring
else:
    strbase = str

def is_tex_buffer(view, point=0):
    # per unofficial docs, match_selector is equivalent to score_selector != 0
    return view.match_selector(point, 'text.tex.latex')

def get_tex_extensions():
    view = sublime.active_window().active_view()
    global_settings = sublime.load_settings('LaTeXTools.sublime-settings')
    tex_file_exts = view.settings().get('tex_file_exts',
        global_settings.get('tex_file_exts', ['.tex']))

    return [s.lower() for s in set(tex_file_exts)]

def is_tex_file(file_name):
    if not isinstance(file_name, strbase):
        raise TypeError('file_name must be a string')

    tex_file_exts = get_tex_extensions()
    for ext in tex_file_exts:
        if file_name.lower().endswith(ext):
            return True
    return False
