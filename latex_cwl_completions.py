# -*- coding:utf-8 -*-
import sublime
import sublime_plugin
import os
import re
import codecs
import threading

index = 0

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    from latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from latex_input_completions import TEX_INPUT_FILE_REGEX
    from getRegion import get_Region
    from getTeXRoot import get_tex_root
    from latextools_utils.subfiles import walk_subfiles
else:
    _ST3 = True
    from .latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from .latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from .latex_input_completions import TEX_INPUT_FILE_REGEX
    from .getRegion import get_Region
    from .getTeXRoot import get_tex_root
    from .latextools_utils.subfiles import walk_subfiles

# Do not do completions in these envrioments
ENV_DONOT_AUTO_COM = [
    OLD_STYLE_CITE_REGEX,
    NEW_STYLE_CITE_REGEX,
    OLD_STYLE_REF_REGEX,
    NEW_STYLE_REF_REGEX,
    TEX_INPUT_FILE_REGEX,
    re.compile(r'\\\\')
]

CWL_COMPLETION = False

class LatexCwlCompletion(sublime_plugin.EventListener):

    def __init__(self):
        self.started = False
        self.completed = False
        self.completions = None
        self.current_file = None
        self._WLOCK = threading.RLock()

    def hack(self):
        sublime.active_window().run_command("hide_auto_complete")
        def hack2():
            sublime.active_window().run_command("auto_complete")
        sublime.set_timeout(hack2, 1)

    def on_completions(self, completions, file_name):
        with self._WLOCK:
            self.started = False
            # we're still on the same file
            if self.current_file == file_name:
                self.completed = True
                self.completions = completions
            else:
                return

        if len(self.completions) != 0:
            sublime.set_timeout(self.hack, 1)

    def on_query_completions(self, view, prefix, locations):
        # settings = sublime.load_settings("LaTeXTools.sublime-settings")
        # cwl_completion = settings.get('cwl_completion')

        if not CWL_COMPLETION:
            return []

        point = locations[0]
        if not view.score_selector(point, "text.tex.latex"):
            return []

        line = view.substr(get_Region(view.line(point).a, point))
        line = line[::-1]

        # Do not do completions in actions
        for rex in ENV_DONOT_AUTO_COM:
            if match(rex, line) != None:
                return []

        if self.completed:
            return (self.completions, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
        elif self.started and self.current_file == view.file_name():
            return

        with self._WLOCK:
            # Get cwl file list
            # cwl_path = sublime.packages_path() + "/LaTeX-cwl"
            settings = sublime.load_settings("LaTeXTools.sublime-settings")
            cwl_file_list = view.settings().get('cwl_list',
                settings.get(
                    'cwl_list',
                    [
                        "tex.cwl",
                        "latex-209.cwl",
                        "latex-document.cwl",
                        "latex-l2tabu.cwl",
                        "latex-mathsymbols.cwl"
                    ]))

            cwl_autoload = view.settings().get(
                'cwl_autoload', settings.get('cwl_autoload', False))

            self.started = True
            self.current_file = view.file_name()
            t = threading.Thread(
                target=CwlParsingHandler(),
                args=(
                    self.on_completions,
                    view.file_name(),
                    cwl_file_list,
                    cwl_autoload
                )
            )
            t.daemon = True
            t.start()

    # This functions is to determine whether LaTeX-cwl is installed,
    # if so, trigger auto-completion in latex buffers by '\'
    def on_activated(self, view):
        point = view.sel()[0].b
        if not view.score_selector(point, "text.tex.latex"):
            return

        # Checking whether LaTeX-cwl is installed
        global CWL_COMPLETION
        if os.path.exists(sublime.packages_path() + "/LaTeX-cwl") or \
           os.path.exists(sublime.installed_packages_path() + "/LaTeX-cwl.sublime-package"):
            CWL_COMPLETION = True

        if CWL_COMPLETION:
            g_settings = sublime.load_settings("Preferences.sublime-settings")
            acts = g_settings.get("auto_complete_triggers", [])

            # Whether auto trigger is already set in Preferences.sublime-settings
            TEX_AUTO_COM = False
            for i in acts:
                if i.get("selector") == "text.tex.latex" and i.get("characters") == "\\":
                    TEX_AUTO_COM = True

            if not TEX_AUTO_COM:
                acts.append({
                    "characters": "\\",
                    "selector": "text.tex.latex"
                })
                g_settings.set("auto_complete_triggers", acts)

def get_packages(root, src):
    packages = []
    for content in walk_subfiles(root, src, preamble_only=True):
        document_classes = re.findall(r'\\documentclass(?:\[[^\]]+\])?\{([^\}]+)\}', content)
        packages.extend(['class-{0}'.format(dc) for dc in document_classes])

        packages.extend(re.findall(r'\\usepackage(?:\[[^\]]+\])?\{([^\}]+)\}', content))
    return packages

# bit of a hack as these are all one cwl file
KOMA_SCRIPT_CLASSES = set(('class-scrartcl', 'class-scrreprt', 'class-book'))

class CwlParsingHandler(object):
    def __init__(self):
        self.callback = None
        self.file_name = None
        self.cwl_file_list = []

    def get_root_file(self):
        root = get_tex_root(sublime.active_window().active_view())
        t = threading.Thread(
            target=self.on_autoload,
            args=(root,)
        )
        t.daemon = True
        t.start()

    def __call__(self, callback, file_name, cwl_file_list, cwl_autoload):
        if cwl_autoload:
            self.callback = callback
            self.file_name = file_name
            self.cwl_file_list = cwl_file_list
            sublime.set_timeout(self.get_root_file)
        else:  # not autoloading... vanillla handler
            callback(parse_cwl_file(cwl_file_list), file_name)

    def on_autoload(self, root):
        cwl_file_list = self.cwl_file_list

        packages = get_packages(os.path.dirname(root), root)

        for package in packages:
            cwl_file = "{0}.cwl".format(package)
            if cwl_file in cwl_file_list:
                continue
            elif package in KOMA_SCRIPT_CLASSES:
                # basic KOMA-Script classes are in one cwl file
                if 'class-scrartcl,scrreprt,scrbook.cwl' not in cwl_file_list:
                    cwl_file_list.append('class-scrartcl,scrreprt,scrbook.cwl')
            elif package == 'polyglossia':
                # polyglossia is more or less babel
                if 'babel.cwl' not in cwl_file_list:
                    cwl_file_list.append('babel.cwl')
            else:
                if os.path.exists(
                    os.path.normpath(os.path.join(
                        sublime.packages_path(), 'LaTeX-cwl', cwl_file))):
                    cwl_file_list.append(cwl_file)
        self.callback(parse_cwl_file(cwl_file_list), self.file_name)

def parse_cwl_file(cwl_file_list):
    # ST3 can use load_resource api, while ST2 do not has this api
    # so a little different with implementation of loading cwl files.
    if _ST3:
        cwl_files = ['Packages/LaTeX-cwl/%s' % x for x in cwl_file_list]
    else:
        cwl_files = [os.path.normpath(sublime.packages_path() + "/LaTeX-cwl/%s" % x) for x in cwl_file_list]

    completions = []
    for cwl in cwl_files:
        if _ST3:
            s = sublime.load_resource(cwl)
        else:
            f = codecs.open(cwl, 'r', 'utf-8')
            try:
                s = u''.join(f.readlines())
            finally:
                f.close()

        # we need some state tracking to ignore keyval data
        # it could be useful at a later date
        KEYVAL = False
        for line in s.split('\n'):
            line = line.lstrip()
            if line == '':
                continue

            if line[0] == '#':
                if line.startswith('#keyvals'):
                    KEYVAL = True
                if line.startswith('#endkeyvals'):
                    KEYVAL = False

                continue

            # ignore TeXStudio's keyval structures
            if KEYVAL:
                continue

            # remove everything after the comment hash
            # again TeXStudio uses this for interesting
            # tracking purposes, but we can ignore it
            line = line.split('#', 1)[0]

            keyword = line.rstrip()
            method = os.path.splitext(os.path.basename(cwl))[0]
            item = (u'%s\t%s' % (keyword, method), parse_keyword(keyword))
            completions.append(item)

    return completions


def parse_keyword(keyword):
    # Replace strings in [] and {} with snippet syntax
    def replace_braces(matchobj):
        global index
        index += 1
        if matchobj.group(1) != None:
            word = matchobj.group(1)
            return u'{${%d:%s}}' % (index, word)
        else:
            word = matchobj.group(2)
            return u'[${%d:%s}]' % (index, word)

    replace, n = re.subn(r'\{([^\{\}\[\]]*)\}|\[([^\{\}\[\]]*)\]', replace_braces, keyword[1:])

    # I do not understand why some of the input will eat the '\' charactor before it!
    # This code is to avoid these things.
    if n == 0 and re.search(r'^[a-zA-Z]+$', keyword[1:].strip()) != None:
            return keyword
    else:
        return replace
