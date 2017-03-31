import sublime

try:
    try:
        from .latextools_utils.cache import _terminate_cache_threadpool
    except (ValueError, ImportError):
        from latextools_utils.cache import _terminate_cache_threadpool
except (ValueError, ImportError):
    pass
else:
    plugin_unloaded = _terminate_cache_threadpool

    if sublime.version() < '3000':
        unload_handler = plugin_unloaded
