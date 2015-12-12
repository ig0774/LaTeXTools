# -*- coding:utf-8 -*-
import sublime
import sublime_plugin
import os
import re
import codecs
import threading
import zipfile

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    from latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from getRegion import get_Region
    from getTeXRoot import get_tex_root
    from latextools_utils import get_setting
    from latextools_utils.is_tex_file import is_tex_file, get_tex_extensions
else:
    _ST3 = True
    from .latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from .latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from .getRegion import get_Region
    from .getTeXRoot import get_tex_root
    from .latextools_utils import get_setting
    from .latextools_utils.is_tex_file import is_tex_file, get_tex_extensions

# Do not do completions in these envrioments
ENV_DONOT_AUTO_COM = [
    OLD_STYLE_CITE_REGEX,
    NEW_STYLE_CITE_REGEX,
    OLD_STYLE_REF_REGEX,
    NEW_STYLE_REF_REGEX,
    re.compile(r'\\\\')
]

# global setting to check whether the LaTeX-cwl package is available or not
CWL_COMPLETION_ENABLED = False

# global instance of CwlCompletions class
CWL_COMPLETIONS = None

# KOMA-Script classes are all in one cwl file
KOMA_SCRIPT_CLASSES = set(('class-scrartcl', 'class-scrreprt', 'class-book'))

# used to detect the end of the preamble
DOCUMENT_START = re.compile(r'\\begin\{document\}')

# CwlCompletions is the manager that coordinates between the event listener
# and the thread that does the actual parsing; it stores the completions after
# they have been parsed, which are retrieved by the get_completions method
class CwlCompletions(object):
    def __init__(self):
        self._started = False
        self._completed = False
        self._triggered = False
        self._completions = None
        self._WLOCK = threading.RLock()

    # get the completions for the specified list of packages
    # packages can be specified either by the name of a cwl file
    # or the package name; document classes should be in the
    # format class-<package>
    def get_completions(self, package_list):
        with self._WLOCK:
            if self._completed:
                self._triggered = False

                cwl_files = set([])
                for package in sorted(set(package_list)):
                    if package.endswith('.cwl'):
                        cwl_file = package
                        package = package[:-4]
                    else:
                        cwl_file = "{0}.cwl".format(package)

                    # some hacks for particular packages that do not match
                    # the standard pattern
                    if package == 'polyglossia':
                        cwl_files.add('babel.cwl')
                    elif package in KOMA_SCRIPT_CLASSES:
                        cwl_files.add('class-scrartcl,scrreprt,scrbook.cwl')
                    else:
                        cwl_files.add(cwl_file)

                completions = []
                cwl_files = sorted(cwl_files)
                for cwl_file in cwl_files:
                    try:
                        completions.extend(self._completions[cwl_file])
                    except KeyError:
                        pass
                return completions
            else:
                self.triggered = True
                if not self.started:
                    self.load_completions()
                return []

    # loads all available completions on a new background thread
    # set force to True to force completions to load regardless
    # of whether they have already been loaded
    def load_completions(self, force=False):
        with self._WLOCK:
            if self._started or self._completed or force:
                return

            self._started = True
            t = threading.Thread(
                target=cwl_parsing_handler,
                args=(
                    self._on_completions,
                )
            )
            t.daemon = True
            t.start()

    # hack to display the autocompletions once they are available
    def _hack(self):
        sublime.active_window().run_command("hide_auto_complete")
        def hack2():
            sublime.active_window().run_command("auto_complete")
        sublime.set_timeout(hack2, 1)

    # callback when completions are loaded
    def _on_completions(self, completions):
        with self._WLOCK:
            self._completions = completions
            self._started = False
            self._completed = True

            # if the user has tried to summon autocompletions, reload
            # now that we have some
            if self._triggered and len(self._completions) != 0:
                sublime.set_timeout(self._hack, 0)

# scans the master file for any packages or documentclasses
def get_packages(rootdir, src, packages):
    if not is_tex_file(src):
        src_tex_file = None
        for ext in get_tex_extensions():
            src_tex_file = ''.join((src, ext))
            if os.path.exists(os.path.join(rootdir, src_tex_file)):
                src = src_tex_file
                break
        if src != src_tex_file:
            print("Could not find file {0}".format(src))
            return

    file_path = os.path.normpath(os.path.join(rootdir, src))
    print("Scanning file: " + repr(file_path))

    try:
        src_file = codecs.open(file_path, "r", 'UTF-8')
    except IOError:
        sublime.status_message("LaTeXTools WARNING: cannot open included file " + file_path)
        print ("WARNING! I can't find it! Check your \\include's and \\input's.")
        return

    try:
        src_content = re.sub("%.*","",src_file.read())
    finally:
        src_file.close()

    m = re.search(r"\\usepackage\[(.*?)\]\{inputenc\}", src_content)
    if m:
        f = None
        try:
            f = codecs.open(file_path, "r", m.group(1))
            src_content = re.sub("%.*", "", f.read())
        except:
            pass
        finally:
            if f and not f.closed:
                f.close()

    # we only care about the preamble, so if we hit \begin{document}, stop
    # processing anything beyond that; we will still process any include or
    # input commands prior to this
    document_start = None
    try:
        src_content, document_start = re.split(DOCUMENT_START, src_content, 1)
    except ValueError:
        # only one result, so no document start
        pass

    document_classes = re.findall(r'\\documentclass(?:\[[^\]]+\])?\{([^\}]+)\}', src_content)
    packages.extend(['class-{0}'.format(dc) for dc in document_classes])
    packages.extend(re.findall(r'\\usepackage(?:\[[^\]]+\])?\{([^\}]+)\}', src_content))

    # search through input tex files recursively
    for f in re.findall(r'\\(?:input|include)\{[^\}]+\}',src_content):
        input_f = re.search(r'\{([^\}]+)', f).group(1)
        get_packages(rootdir, input_f, packages)


def _is_snippet(completion_entry):
    """
    returns True if the second part of the completion tuple
    is a sublime snippet
    """
    completion_result = completion_entry[1]
    return completion_result[0] == '\\' and '${1:' in completion_result


class LatexCwlCompletion(sublime_plugin.EventListener):

    def on_query_completions(self, view, prefix, locations):
        if not CWL_COMPLETION_ENABLED:
            return []

        point = locations[0]
        if not view.score_selector(point, "text.tex.latex"):
            return []

        point_before = point - len(prefix)
        char_before = view.substr(get_Region(point_before - 1, point_before))
        if not _ST3:  # convert from unicode (might not be necessary)
            char_before = char_before.encode("utf-8")
        is_prefixed = char_before == "\\"

        completion_level = "prefixed"  # default completion level is "prefixed"
        completion_level = get_setting("command_completion",
                                       completion_level)

        do_complete = {
            "never": False,
            "prefixed": is_prefixed,
            "always": True
        }.get(completion_level, is_prefixed)
        if not do_complete:
            return []

        line = view.substr(get_Region(view.line(point).a, point))
        line = line[::-1]

        # Do not do completions in actions
        for rex in ENV_DONOT_AUTO_COM:
            if match(rex, line) is not None:
                return []

        # get the current documents package list
        packages = get_setting('cwl_list', [
            "tex.cwl",
            "latex-209.cwl",
            "latex-document.cwl",
            "latex-l2tabu.cwl",
            "latex-mathsymbols.cwl"
        ])

        if get_setting('cwl_autoload', True):
            texroot = get_tex_root(view)
            get_packages(os.path.split(texroot)[0], texroot, packages)

        if not packages:
            return []

        # load the completions for the document
        completions = CWL_COMPLETIONS.get_completions(packages)

        # autocompleting with slash already on line
        # this is necessary to work around a short-coming in ST where having a keyed entry
        # appears to interfere with it recognising that there is a \ already on the line
        #
        # NB this may not work if there are other punctuation marks in the completion
        if is_prefixed:
            completions = [(c[0], c[1][1:]) if _is_snippet(c) else c
                           for c in completions]
        return (completions, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)

    # This functions is to determine whether LaTeX-cwl is installed,
    # if so, trigger auto-completion in latex buffers by '\'
    def on_activated(self, view):
        point = view.sel()[0].b
        if not view.score_selector(point, "text.tex.latex"):
            return

        # Checking whether LaTeX-cwl is installed
        global CWL_COMPLETION_ENABLED
        if os.path.exists(sublime.packages_path() + "/LaTeX-cwl") or \
            os.path.exists(sublime.installed_packages_path() + "/LaTeX-cwl.sublime-package"):
            CWL_COMPLETION_ENABLED = True

        if CWL_COMPLETION_ENABLED:
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

    # used to ensure that completions are loaded whenever a LaTeX document
    # is loaded
    def on_load_async(self, view):
        point = view.sel()[0].end()
        if not view.score_selector(point, "text.tex.latex"):
            return

        CWL_COMPLETIONS.load_completions()

# ST2 does not support async methods
if not _ST3:
    LatexCwlCompletion.on_load = LatexCwlCompletion.on_load_async


# this is the function called by the CwlCompletions class to handle parsing
# it loads every cwl in turn and returns a dictionary mapping from the
# cwl file name to the set of parsed completions
def cwl_parsing_handler(callback):
    results = {}
    cwl_files, use_package = get_cwl_package_files()

    for cwl_file in cwl_files:
        if use_package:
            cwl = 'Packages/LaTeX-cwl/{0}'.format(cwl_file)
            try:
                s = sublime.load_resource(cwl)
            except IOError:
                print(cwl_file + ' does not exist or could not be accessed')
                continue
        else:
            cwl = os.path.join(
                sublime.packages_path(),
                'LaTeX-cwl',
                cwl_file
            )

            try:
                f = codecs.open(cwl, 'r', 'utf-8')
            except IOError:
                print(cwl_file + ' does not exist or could not be accessed')
                continue
            else:
                try:
                    s = u''.join(f.readlines())
                finally:
                    f.close()

        completions = parse_cwl_file(cwl, s)
        results[cwl_file] = completions

    callback(results)


# gets a list of all cwl package files available, whether in the
# sublime-package file or an exploded directory; returns a tuple
# consisting of the list of cwl files and a boolean indicating
# whether it is in a .sublime-package file or an expanded directory
def get_cwl_package_files():
    package_path = os.path.join(
        sublime.packages_path(),
        'LaTeX-cwl'
    )

    if os.path.exists(package_path):
        result = []
        for root, dirs, files in os.walk(package_path):
            temp = root.replace(package_path, "")
            for file_name in files:
                result.append(os.path.join(temp, file_name))
        return (result, False)
    elif _ST3:
        package_path = os.path.join(
            sublime.installed_packages_path(),
            'LaTeX-cwl.sublime-package'
        )

        if not os.path.exists(package_path):
            return ([], False)

        with zipfile.ZipFile(package_path) as zip_file:
            return (zip_file.namelist(), True)

    # somehow this function got called with a cwl package existing
    return ([], False)

# actually does the parsing of the cwl files
def parse_cwl_file(cwl, s):
    completions = []
    for line in s.split('\n'):
        line = line.strip()
        if line == '':
            continue
        if line[0] == '#':
            continue

        keyword = line.strip()
        method = os.path.splitext(os.path.basename(cwl))[0]
        item = (u'%s\t%s' % (keyword, method), parse_keyword(keyword))
        completions.append(item)

    return completions


def parse_keyword(keyword):
    # Replace strings in [] and {} with snippet syntax
    def replace_braces(matchobj):
        replace_braces.index += 1
        if matchobj.group(1) != None:
            word = matchobj.group(1)
            return u'{${%d:%s}}' % (replace_braces.index, word)
        else:
            word = matchobj.group(2)
            return u'[${%d:%s}]' % (replace_braces.index, word)
    replace_braces.index = 0

    replace, n = re.subn(r'\{([^\{\}\[\]]*)\}|\[([^\{\}\[\]]*)\]', replace_braces, keyword)

    # I do not understand why some of the input will eat the '\' charactor before it!
    # This code is to avoid these things.
    if n == 0 and re.search(r'^[a-zA-Z]+$', keyword[1:].strip()) != None:
        return keyword
    else:
        return replace


# ensure that CWL_COMPLETIONS has a value
# its better to do it here because its more stable across reloads
def plugin_loaded():
    global CWL_COMPLETIONS
    if CWL_COMPLETIONS is None:
        CWL_COMPLETIONS = CwlCompletions()

if not _ST3:
    plugin_loaded()
