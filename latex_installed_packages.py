# -*- coding:utf-8 -*-
from __future__ import print_function
import sublime
import sublime_plugin

import os
import json

from collections import defaultdict

import threading

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    strbase = basestring
    from latextools_utils.external_command import external_command
    import sys
else:
    _ST3 = True
    strbase = str
    from .latextools_utils.external_command import external_command

__all__ = ['LatexGenPkgCacheCommand']

def _get_tex_searchpath(file_type):
    if file_type is None:
        raise Exception('file_type must be set for _get_tex_searchpath')

    command = ['kpsewhich']
    command.append('--show-path={0}'.format(file_type))

    try:
        return_code, paths, _ = external_command(command)
        if return_code == 0:
            return paths
        else:
            sublime.error_message('An error occurred while trying to run kpsewhich. TEXMF tree could not be accessed.')
    except OSError:
        sublime.error_message('Could not run kpsewhich. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.')

    return None

def _get_files_matching_extensions(paths, extensions=[]):
    if isinstance(extensions, strbase):
        extensions = [extensions]

    matched_files = defaultdict(lambda: [])

    for path in paths.split(os.pathsep):
        # bad idea... also our current directory isn't meaningful from a WindowCommand
        if path == '.':
            continue

        # !! sometimes occurs in the results on POSIX; remove them
        path = path.replace(u'!!', u'')
        path = os.path.normpath(path)
        if not os.path.exists(path):  # ensure path exists
            continue

        if len(extensions) > 0:
            for _, _, files in os.walk(path):
                for f in files:
                    for ext in extensions:
                        if f.endswith(u''.join((os.extsep, ext))):
                            matched_files[ext].append(os.path.splitext(f)[0])
        else:
            for _, _, files in os.walk(path):
                for f in files:
                    matched_files['*'].append(os.path.splitext(f)[0])

    matched_files = dict([(key, sorted(set(value), key=lambda s: s.lower()))
        for key, value in matched_files.items()])

    return matched_files

def _generate_package_cache():
    installed_tex_items = _get_files_matching_extensions(
        _get_tex_searchpath('tex'),
        ['sty', 'cls']
    )

    installed_bst = _get_files_matching_extensions(
        _get_tex_searchpath('bst'),
        ['bst']
    )

    # create the cache object
    pkg_cache = {
        'pkg': installed_tex_items['sty'],
        'bst': installed_bst['bst'],
        'cls': installed_tex_items['cls']
    }

    # For ST3, put the cache files in cache dir
    # and for ST2, put it in the user packages dir
    # and change the name
    if _ST3:
        cache_path = os.path.normpath(
            os.path.join(
                sublime.cache_path(),
                "LaTeXTools"
            ))
    else:
        cache_path = os.path.normpath(
            os.path.join(
                sublime.packages_path(),
                "User"
            ))

    if not os.path.exists(cache_path):
        os.makedirs(cache_path)

    pkg_cache_file = os.path.normpath(
        os.path.join(cache_path, 'pkg_cache.cache' if _ST3 else 'latextools_pkg_cache.cache'))

    with open(pkg_cache_file, 'w+') as f:
        json.dump(pkg_cache, f)

    sublime.status_message('Finished generating LaTeX package cache')

# Generates a cache for installed latex packages, classes and bst.
# Used for fill all command for \documentclass, \usepackage and
# \bibliographystyle envrioments
class LatexGenPkgCacheCommand(sublime_plugin.WindowCommand):

    def run(self):
        if _ST3:
            # on ST3+, use a separate thread to generate the package cache
            thread = threading.Thread(target=_generate_package_cache)
            thread.daemon = True
            thread.start()
        else:
            # on ST2, sublime API must be accessed from main thread so...
            _generate_package_cache()
