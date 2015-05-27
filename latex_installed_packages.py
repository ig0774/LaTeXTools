# -*- coding:utf-8 -*-
from __future__ import print_function
import sublime
import sublime_plugin

import subprocess
from subprocess import Popen, PIPE

import os
import json

from collections import defaultdict

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    strbase = basestring
    from get_texpath import get_texpath
else:
    _ST3 = True
    strbase = str
    from .get_texpath import get_texpath

__all__ = ['LatexGenPkgCacheCommand']

def _get_tex_searchpath(file_type):
    if file_type is None:
        raise Exception('file_type must be set for _get_tex_searchpath')

    command = ['kpsewhich']
    command.append('--show-path={}'.format(file_type))

    texpath = get_texpath() or os.environ['PATH']
    env = dict(os.environ)
    env['PATH'] = texpath

    try:
        # Windows-specific adjustments
        startupinfo = None
        shell = False
        if sublime.platform() == 'windows':
            # ensure console window doesn't show
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            shell = True

        print('Running %s' % (' '.join(command)))
        p = Popen(
            command,
            stdout=PIPE,
            stdin=PIPE,
            startupinfo=startupinfo,
            shell=shell,
            env=env
        )

        paths = p.communicate()[0].decode('utf-8').rstrip()
        if p.returncode == 0:
            return paths
        else:
            sublime.eror_message('An error occurred while trying to run kpsewhich. TEXMF tree could not be accessed.')
    except OSError:
        sublime.error_message('Could not run kpsewhich. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.')

    return None

def _get_files_matching_extensions(paths, extensions=[]):
    if isinstance(extensions, strbase):
        extensions = [extensions]

    matched_files = defaultdict(lambda: [])

    for path in paths.split(os.pathsep):
        # !! sometimes occurs in the results on POSIX; remove them
        path = path.replace('!!', '')
        path = os.path.normpath(path)
        if not os.path.exists(path):  # ensure path exists
            continue

        if len(extensions) > 0:
            for _, _, files in os.walk(path):
                for f in files:
                    for ext in extensions:
                        if f.endswith(''.join((os.extsep, ext))):
                            matched_files[ext].append(os.path.splitext(f)[0])
        else:
            for _, _, files in os.walk(path):
                for f in files:
                    matched_files['*'].append(os.path.splitext(f)[0])

    return matched_files

# Generates a cache for installed latex packages, classes and bst.
# Used for fill all command for \documentclass, \usepackage and
# \bibliographystyle envrioments
class LatexGenPkgCacheCommand(sublime_plugin.WindowCommand):

    def run(self):
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
        # and for ST2, put it in package dir
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
                    "LaTeXTools"
                ))

        if not os.path.exists(cache_path):
            os.makedirs(cache_path)

        pkg_cache_file = os.path.normpath(
            os.path.join(cache_path, 'pkg_cache.cache'))

        with open(pkg_cache_file, 'w+') as f:
            json.dump(pkg_cache, f)
