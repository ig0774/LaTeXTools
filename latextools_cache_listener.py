from __future__ import unicode_literals, print_function

import sublime
import sublime_plugin

import collections
from functools import partial
import threading
import time
import traceback

try:
    from .latex_cite_completions import (
        find_bib_files, run_plugin_command
    )
    from .latextools_utils import analysis, get_setting
    from .latextools_utils.bibcache import BibCache
    from .latextools_utils.cache import LocalCache
    from .latextools_utils.tex_directives import get_tex_root
    from .latextools_utils.progress_indicator import ProgressIndicator
except (ValueError, ImportError):
    from latex_cite_completions import (
        find_bib_files, run_plugin_command
    )
    from latextools_utils import analysis, get_setting
    from latextools_utils.bibcache import BibCache
    from latextools_utils.cache import LocalCache
    from latextools_utils.tex_directives import get_tex_root
    from latextools_utils.progress_indicator import ProgressIndicator

_ST3 = sublime.version() >= '3000'


class LatextoolsCacheUpdater(object):

    def __init__(self):
        super(LatextoolsCacheUpdater, self).__init__()
        self._steps = []

    def add_step(self, step):
        if step is None:
            raise ValueError('step cannot be None')
        elif not callable(step):
            raise TypeError('step must be a no-args function')

        self._steps.append(step)

    def run_cache_update(self):
        t = threading.Thread(target=self._run_cache_update)
        t.daemon = True
        t.start()

        ProgressIndicator(
            t, 'Updating LaTeXTools cache', 'LaTeXTools cache updated')

        return t

    def _run_cache_update(self):
        for step in self._steps:
            try:
                step()
            except Exception:
                traceback.print_exc()


class LatextoolsAnalysisUpdater(LatextoolsCacheUpdater):

    def run_analysis(self, tex_root):
        self.add_step(partial(self._run_analysis, tex_root))

    def _run_analysis(self, tex_root):
        ana = analysis.analyze_document(tex_root)

        local_cache = LocalCache(tex_root)
        with local_cache._write_lock:
            local_cache.invalidate()
            local_cache.set('analysis', ana)


class LatextoolsBibCacheUpdater(LatextoolsCacheUpdater):

    def run_bib_cache(self, tex_root):
        self.add_step(partial(self._invalidate_find_bib_files, tex_root))
        self.add_step(partial(self._run_bib_cache, tex_root))

    def _invalidate_find_bib_files(self, tex_root):
        LocalCache(tex_root).invalidate('bib_files')

    def _run_bib_cache(self, tex_root):
        run_plugin_command('get_entries', *(find_bib_files(tex_root) or []))


class LatextoolsCacheUpdateListener(
    sublime_plugin.EventListener, LatextoolsAnalysisUpdater,
    LatextoolsBibCacheUpdater
):

    # stores a cache instance per open LaTeX view
    # note that cache instances share state
    _TEX_CACHES = {}
    _TEX_ROOT_REFS = collections.defaultdict(lambda: 0)
    _BIB_CACHES = {}
    _UPDATING_DOCS_LOCK = threading.RLock()
    _UPDATING_DOCS = set([])

    def on_load_async(self, view):
        if not view.score_selector(0, 'text.tex.latex'):
            return
        on_load = get_setting('cache_on_load', {}, view=view)
        if not on_load or not any(on_load.values()):
            return

        tex_root = get_tex_root(view)
        if tex_root is None:
            return

        self._TEX_CACHES[view.id()] = local_cache = LocalCache(tex_root)
        self._TEX_ROOT_REFS[tex_root] += 1

        # because cache state is shared amongst all documents sharing a tex
        # root, this ensure we only load the analysis ONCE in the on_load
        # event
        if (
            not local_cache.has('analysis') and
            on_load.get('analysis', False)
        ):
            self.run_analysis(tex_root)

        if tex_root not in self._BIB_CACHES:
            if on_load.get('bibliography', False):
                self.run_bib_cache(tex_root)

            self._BIB_CACHES[tex_root] = bib_caches = []

            bib_files = find_bib_files(tex_root)

            plugins = get_setting(
                'bibliography_plugins', ['traditional'], view=view)

            if not isinstance(plugins, list):
                plugins = [plugins]

            if 'new' in plugins or 'new_bibliography' in plugins:
                for bib_file in bib_files:
                    bib_caches.append(BibCache('new', bib_file))

            if (
                'traditional' in plugins or
                'traditional_bibliography' in plugins
            ):
                for bib_file in bib_files:
                    bib_caches.append(BibCache('trad', bib_file))

        with self._UPDATING_DOCS_LOCK:
            self._UPDATING_DOCS.add(tex_root)
        t = self.run_cache_update()
        self._monitor_update_thread(t, tex_root)

    def on_close(self, view):
        if not view.score_selector(0, 'text.tex.latex'):
            return

        _id = view.id()

        try:
            tex_root = self._TEX_CACHES[_id].tex_root
            self._TEX_ROOT_REFS[tex_root] -= 1
            if self._TEX_ROOT_REFS[tex_root] <= 0:
                del self._TEX_ROOT_REFS[tex_root]
                del self._BIB_CACHES[tex_root]
        except Exception:
            pass

        try:
            del self._TEX_CACHES[_id]
        except Exception:
            pass

        try:
            del self._LAST_CHANGE_COUNT[_id]
        except Exception:
            pass

    def on_post_save_async(self, view):
        if not view.score_selector(0, 'text.tex.latex'):
            return

        on_save = get_setting('cache_on_save', {}, view=view)
        if not on_save or not any(on_save.values()):
            return

        if not self._should_update(view):
            return

        tex_root = get_tex_root(view)
        if tex_root is None:
            return

        with self._UPDATING_DOCS_LOCK:
            if tex_root in self._UPDATING_DOCS:
                return

        _id = view.id()
        if _id not in self._TEX_CACHES:
            self._TEX_CACHES[_id] = LocalCache(tex_root)

        if on_save.get('analysis', False):
            self.run_analysis(tex_root)

        if on_save.get('bibliography', False):
            self.run_bib_cache(tex_root)

        with self._UPDATING_DOCS_LOCK:
            self._UPDATING_DOCS.add(tex_root)
        t = self.run_cache_update()
        self._monitor_update_thread(t, tex_root)

    if not _ST3:
        on_load = on_load_async
        on_post_save = on_post_save_async

        _SHOULD_UPDATE_VIEWS = set([])

        def on_pre_save(self, view):
            if not view.score_selector(0, 'text.tex.latex'):
                return

            on_save = get_setting('cache_on_save', {}, view=view)
            if not on_save or not any(on_save.values()):
                return

            if view.is_dirty():
                self._SHOULD_UPDATE_VIEWS.add(view.id())

        def _should_update(self, view):
            _id = view.id()
            if _id in self._SHOULD_UPDATE_VIEWS:
                self._SHOULD_UPDATE_VIEWS.remove(_id)
                return True
            return False
    else:
        _LAST_CHANGE_COUNT = collections.defaultdict(lambda: 0)

        def _should_update(self, view):
            _id = view.id()
            change_count = view.change_count()
            if change_count > self._LAST_CHANGE_COUNT.get(_id):
                self._LAST_CHANGE_COUNT[_id] = change_count
                return True
            return False

    def _monitor_update_thread(self, t, tex_root):
        monitor = threading.Thread(
            target=self.__monitor_thread, args=(t, tex_root))
        monitor.daemon = True
        monitor.start()

    def __monitor_thread(self, t, tex_root):
        while t.is_alive():
            time.sleep(0.1)

        with self._UPDATING_DOCS_LOCK:
            try:
                self._UPDATING_DOCS.remove(tex_root)
            except KeyError:
                pass


class LatextoolsCacheUpdateCommand(object):

    def is_visible(self):
        return sublime.active_window().active_view().score_selector(
            0, 'text.tex.latex'
        ) > 0


class LatextoolsAnalysisUpdateCommand(
    sublime_plugin.TextCommand, LatextoolsCacheUpdateCommand,
    LatextoolsAnalysisUpdater
):

    def __init__(self, *args, **kwargs):
        super(LatextoolsAnalysisUpdateCommand, self).__init__(*args, **kwargs)

    def run(self, edit):
        if not self.view.score_selector(0, 'text.tex.latex'):
            return

        tex_root = get_tex_root(self.view)
        if tex_root is None:
            return

        self.run_analysis(tex_root)
        self.run_cache_update()


class LatextoolsBibcacheUpdateCommand(
    sublime_plugin.TextCommand, LatextoolsCacheUpdateCommand,
    LatextoolsBibCacheUpdater
):

    def __init__(self, *args, **kwargs):
        super(LatextoolsBibcacheUpdateCommand, self).__init__(*args, **kwargs)

    def run(self, edit):
        if not self.view.score_selector(0, 'text.tex.latex'):
            return

        tex_root = get_tex_root(self.view)
        if tex_root is None:
            return

        self.run_bib_cache(tex_root)
        self.run_cache_update()
