import hashlib
import json
import os
import sublime
import sys
import tempfile

try:
    from latextools_utils.tex_directives import (
        get_tex_root, parse_tex_directives
    )
    from latextools_utils.sublime_utils import get_project_file_name
except ImportError:
    from .tex_directives import get_tex_root, parse_tex_directives
    from .sublime_utils import get_project_file_name


__all__ = ['get_aux_directory', 'get_output_directory', 'UnsavedFileException']


# raised whenever the root cannot be determined, which indicates an unsaved
# file
class UnsavedFileException(Exception):
    pass


# finds the aux-directory
# general algorithm:
#   1. check for an explicit aux_directory directory
#   2. check for an --aux-directory flag
#   3. check for a project setting
#   4. check for a global setting
#   5. assume aux_directory is the same as output_directory
def get_aux_directory(view_or_root):
    root = get_root(view_or_root)

    aux_directory = None
    if root is not None:
        aux_directory = get_directive(root, 'aux_directory')

    if aux_directory is not None and aux_directory != '':
        return resolve_to_absolute_path(
            root, aux_directory, _get_root_directory(root)
        )

    view = sublime.active_window().active_view()
    aux_directory = view.settings().get('aux_directory')

    if aux_directory is not None and aux_directory != '':
        return resolve_to_absolute_path(
            root,
            aux_directory,
            _get_root_directory(get_project_file_name(view))
        )

    settings = sublime.load_settings('LaTeXTools.sublime-settings')
    aux_directory = settings.get('aux_directory')

    if aux_directory is not None and aux_directory != '':
        return resolve_to_absolute_path(
            root, aux_directory, _get_root_directory(root)
        )

    return get_output_directory(root)


# finds the output-directory
# general algorithm:
#   1. check for an explicit output_directory directive
#   2. check for an --output-directory flag
#   3. check for a project setting
#   4. check for a global setting
#   5. assume output_directory is None
def get_output_directory(view_or_root):
    root = get_root(view_or_root)

    output_directory = None
    if root is not None:
        output_directory = get_directive(root, 'output_directory')

    if output_directory is not None and output_directory != '':
        return resolve_to_absolute_path(
            root, output_directory, _get_root_directory(root)
        )

    view = sublime.active_window().active_view()
    output_directory = view.settings().get('output_directory')

    if output_directory is not None and output_directory != '':
        return resolve_to_absolute_path(
            root,
            output_directory,
            _get_root_directory(get_project_file_name(view))
        )

    settings = sublime.load_settings('LaTeXTools.sublime-settings')
    output_directory = settings.get('output_directory')

    if output_directory is not None and output_directory != '':
        return resolve_to_absolute_path(
            root, output_directory, _get_root_directory(root)
        )

    return None


def get_root(view_or_root):
    if isinstance(view_or_root, sublime.View):
        # here we can still handle root being None if the output_directory
        # setting is an aboslute path
        return get_tex_root(view_or_root)
    else:
        return view_or_root


def get_directive(root, key):
    directives = parse_tex_directives(
        root, multi_values=['options'], only_for=['options', 'key']
    )

    try:
        return directives[key]
    except KeyError:
        option = key.replace('_', '-')
        for opt in directives.get('options', []):
            if opt.lstrip('-').startswith(option):
                try:
                    return opt.split('=')[1].strip()
                except:
                    # invalid option parameter
                    return None
        return None


def resolve_to_absolute_path(root, value, root_path):
    # special values
    if (
        len(value) > 4 and
        value[0] == '<' and
        value[1] == '<' and
        value[-2] == '>' and
        value[-1] == '>'
    ):
        root_hash = _get_root_hash(root)
        if root_hash is None:
            raise UnsavedFileException()

        if value == '<<temp>>':
            result = os.path.join(
                _get_tmp_dir(), root_hash
            )
        elif value == '<<project>>':
            result = os.path.join(
                root_path, root_hash
            )
        elif value == '<<cache>>':
            result = os.path.join(
                get_cache_directory(),
                root_hash
            )
        else:
            print(u'unrecognized special value: {0}'.format(value))

            # NOTE this assumes that the value provided is a typo, etc.
            # and tries not to do anything harmful. This may not be the
            # best assumption
            return None

        # create the directory
        make_dirs(result)

        return result

    result = os.path.expandvars(
        os.path.expanduser(
            value
        )
    )

    if os.path.isabs(result):
        return os.path.normpath(result)
    else:
        return os.path.normpath(
            os.path.join(
                root_path,
                result
            )
        )


# wrapper for os.makedirs which will not raise an error is path already
# exists
def make_dirs(path):
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.exists(path):
            reraise(*sys.exc_info())


if sys.version_info < (3,):
    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")

else:
    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value


if sublime.version() < '3000':
    def get_cache_directory():
        return os.path.join(
            sublime.packages_path(),
            'User',
            '.lt_cache'
        )
else:
    def get_cache_directory():
        return os.path.join(
            sublime.cache_path(),
            'LaTeXTools'
        )


# uses a process-wide temp directory which should be cleaned-up on exit
def _get_tmp_dir():
    if hasattr(_get_tmp_dir, 'directory'):
        return _get_tmp_dir.directory
    else:
        _get_tmp_dir.directory = tempfile.mkdtemp()

        # register directory to be deleted on next start-up
        # unfortunately, there is no reliable way to do clean-up on exit
        # see https://github.com/SublimeTextIssues/Core/issues/10
        cache_dir = get_cache_directory()
        make_dirs(cache_dir)

        temporary_output_dirs = os.path.join(
            cache_dir,
            'temporary_output_dirs'
        )

        if os.path.exists(temporary_output_dirs):
            with open(temporary_output_dirs, 'r') as f:
                data = json.load(f)
        else:
            data = {'directories': []}

        data['directories'].append(_get_tmp_dir.directory)

        with open(temporary_output_dirs, 'w') as f:
            json.dump(data, f)

        return _get_tmp_dir.directory


def _get_root_directory(root):
    if root is None:
        # best guess
        return os.getcwd()
    else:
        if not os.path.isabs(root):
            # again, best guess
            return os.path.join(os.getcwd(), os.path.dirname(root))
        return os.path.dirname(root)


def _get_root_hash(root):
    if root is None:
        return None

    return hashlib.md5(root.encode('utf-8')).hexdigest()
