import hashlib
import json
import os
import sublime
import sys
import tempfile

try:
    from latextools_utils.settings import get_setting
    from latextools_utils.tex_directives import get_tex_root, parse_tex_directives
except ImportError:
    from .settings import get_setting
    from .tex_directives import get_tex_root, parse_tex_directives


__all__ = ['get_output_directory']


# raised whenever the root cannot be determined, which indicates an unsaved
# file
class UnsavedFileException(Exception):
    pass


def get_output_directory(view_or_root):
    output_directory = None

    if isinstance(view_or_root, sublime.View):
        # here we can still handle root being None if the output_directory
        # setting is an aboslute path
        root = get_tex_root(view_or_root)
    else:
        root = view_or_root

    if root is None:
        output_directory = get_setting('output_directory')
    else:
        directives = parse_tex_directives(root, only_for=['output_directory'])
        try:
            output_directory = directives['output_directory']
        except KeyError:
            output_directory = get_setting('output_directory')

    if output_directory is None or output_directory == '':
        return None
    else:
        # special values
        if (
            len(output_directory) > 4 and
            output_directory[0] == '<' and
            output_directory[1] == '<' and
            output_directory[-2] == '>' and
            output_directory[-1] == '>'
        ):
            root_hash = _get_root_hash(root)
            if root_hash is None:
                raise UnsavedFileException()

            if output_directory == '<<temp>>':
                output_directory = os.path.join(
                    _get_tmp_dir(), root_hash
                )
            elif output_directory == '<<project>>':
                output_directory = os.path.join(
                    _get_root_directory(root), root_hash
                )
            elif output_directory == '<<cache>>':
                output_directory = os.path.join(
                    get_cache_directory(),
                    root_hash
                )
            else:
                print(u'unrecognized special value: {0}'.format(
                    output_directory
                ))

                # NOTE this assumes that the value provided is a typo, etc.
                # and tries not to do anything harmful. This may not be the
                # best assumption
                return None

            # create the directory
            make_dirs(output_directory)

            return output_directory

        output_directory = os.path.expandvars(
            os.path.expanduser(
                output_directory
            )
        )

        if os.path.isabs(output_directory):
            return os.path.normpath(output_directory)
        else:
            root_dir = _get_root_directory(root)
            if root_dir is None:
                raise UnsavedFileException()

            return os.path.normpath(
                os.path.join(
                    root_dir,
                    output_directory
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
