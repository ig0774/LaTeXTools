# ST2/ST3 compat
from __future__ import print_function
import sublime

import os, os.path
import sys
sys.path.append(os.path.dirname(__file__))

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    import getTeXRoot
    import latex_chars
    
    import latex_commands_grammar
    from latex_commands_grammar import remove_latex_commands

    import kpsewhich
    from kpsewhich import kpsewhich
else:
    _ST3 = True
    from . import getTeXRoot
    from . import latex_chars
    from .latex_commands_grammar import remove_latex_commands
    from .kpsewhich import kpsewhich

import sublime_plugin
import re
import codecs

import pybtex
from pybtex.bibtex.utils import split_name_list

from string import Formatter
from collections import MutableMapping

# LaTeX -> Unicode decoder
latex_chars.register()

class UnrecognizedCiteFormatError(Exception): pass
class NoBibFilesError(Exception): pass

class BibParsingError(Exception):
    def __init__(self, filename="", message=""):
        super(BibParsingError, self).__init__(message)
        self.filename = filename

OLD_STYLE_CITE_REGEX = re.compile(r"([^_]*_)?([a-zX*]*?)etic(?:\\|\b)")
# I apoligise profusely for this regex
# forward version with explanation:
# \\
#    (?:
#       (?# 
#           first branch matches \foreigntextquote, 
#           \hypentextquote, \foreignblockquote, \hyphenblockquote,
#           \hybridblockquote and starred versions
#           syntax is:
#           \foreigntextquote{lang}[key][punct]{text}
#       )
#       (?:foreign|hyphen|hybrid(?=block))(?:text|block)quote\*?
#           \{[^}]*\}\[(?:(?:[^[\],]*,)*)?|
#       (?#
#           second branch matches \textquote, \blockquote and
#           starred versions
#           syntax is:
#           \textquote[key]{text}
#       )
#       (?:text|block)quote\*?\[(?:(?:[^[\],]*,)*)?|
#       (?#
#           third branch matches \foreigntextcquote,
#           \hyphentextcquote, \foreignblockcquote, \hypenblockcquote,
#           \hybridblockcquote and starred versions
#           syntax is:
#           \foreigntextcquote{lang}[prenote][postnote]{key}{text}
#       )
#       (?:foreign|hyphen|hybrid(?=block))(?:text|block)cquote\*?
#           \{[^}]*\}(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?|
#       (?#
#           fourth branch matches \textcquote, \blockcquote and 
#           starred versions
#           syntax is:
#           \textcquote[prenote][postnote]{key}{text}
#       )
#       (?:text|block)cquote\*?(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?|
#       (?#
#           fifth branch matches \volcite and friends
#           syntax is:
#           \volcite[prenote]{volume}[page]{key}
#       )
#       (?:p|P|f|ft|s|S|t|T|a|A)?volcite
#           (?:\[[^\]]*\])?\{[^}]*\}(?:\[[^\]]*\])?\{(?:(?:[^{},]*,)*)?|
#       (?#
#           sixth branch matches \volcites and friends
#           syntax is:
#           \volcites(multiprenote)(multipostnote)[prenote]{volume}[page]{key}
#               ...[prenote]{volume}[page]{key}
#       )
#       (?:p|P|f|ft|s|S|t|T|a|A)?volcites
#           (?:\([^)]*\)){0,2}
#               (?:(?:\[[^\]]*\])?\{[^}]*\}
#               (?:\[[^\]]*\])?\{(?:(?:[^{},]*,)*)?(?:\}(?=.*?\{))?){1,}|
#       (?#
#           seventh branch matches \cites and friends, excluding \volcite
#           syntax is:
#           \cites(multiprenote)(multipostnote)[prenote][postnote]{key}
#               ...[prenote][postnote]{key}
#       )
#       (?:(?!(?:p|P|f|ft|s|S|t|T|a|A)?volcites)
#           (?:[A-Z]?[a-z]*c)|C)ites
#           (?:\([^)]*\)){0,2}
#           (?:(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?(?:\}(?=.*?\{))?){1,}|
#       (?#
#           eighth branch matches most everything else, excluding \volcite,
#           \mcite, \citereset and \citestyle
#           syntax is:
#           \cite[<prenote>][<postnote>]{key}
#       )
#       (?:(?!(?:p|P|f|ft|s|S|t|T|a|A)?volcite|mcite)
#           (?:[A-Z]?[a-z]*c)|C)ite(?!reset|style)([a-zX*]*?)
#           ([.*?]){0,2}(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?|
#       (?#
#           ninth branch matches apacite commands
#           syntax is:
#           \citeA<prenote>[postnote]{key}
#       )
#       cite(?:(?:author|year)(?:NP)?|NP|A)?(?:<[^>]*>)?(?:\[[^\]]*\])?\{(?:(?:[^{},]*,)*)?)$
NEW_STYLE_CITE_REGEX = re.compile(
    r"""(?:
            (?# 
                first branch matches \foreigntextquote, 
                \hypentextquote, \foreignblockquote, \hyphenblockquote,
                \hybridblockquote and starred versions
                syntax is:
                \foreigntextquote{lang}[key][punct]{text}
            )
            (?:(?P<prefix1>[^\[\],]*)(?:,[^\[\],]*)*\[\}[^\{]*\{
                \*?etouq(?:kcolb|txet)(?:ngierof|nehpyh|(?<=kcolb)dirbyh))|
            (?#
                second branch matches \textquote, \blockquote and
                starred versions
                syntax is:
                \textquote[key]{text}
            )
            (?:(?P<prefix2>[^\[\],]*)(?:,[^\[\],]*)*\[\*?etouq(?:kcolb|txet))|
            (?#
                third branch matches \foreigntextcquote,
                \hyphentextcquote, \foreignblockcquote, \hypenblockcquote,
                \hybridblockcquote and starred versions
                syntax is:
                \foreigntextcquote{lang}[prenote][postnote]{key}{text}
            )
            (?:(?P<prefix3>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}\}[^\{]*\{
                \*?etouqc(?:kcolb|txet)(?:ngierof|nehpyh|(?<=kcolb)dirbyh))|
            (?#
                fourth branch matches \textcquote, \blockcquote and 
                starred versions
                syntax is:
                \textcquote[prenote][postnote]{key}{text}
            )
            (?:(?P<prefix4>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                \*?etouqc(?:kcolb|txet))|
            (?#
                fifth branch matches \volcite and friends
                syntax is:
                \volcite[prenote]{volume}[page]{key}
            )
            (?:(?P<prefix5>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?
                eticlov(?:p|P|f|ft|s|S|t|T|a|A)?)|
            (?#
                sixth branch matches \volcites and friends
            )
            (?:(?P<prefix6>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?
                (?:\}[^\{}]*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?)*
                (?:\)[^(]*\(){0,2}
                seticlov(?:p|P|f|ft|s|S|t|T|a|A)?)|
            (?#
                seventh branch matches \cites and friends, excluding \volcite
            )
            (?:(?P<prefix7>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                (?:\}[^\}]*\{(?:\][^\[]*\[){0,2})*
                (?:[\.\*\?]){0,2}(?:\)[^(]*\(){0,2}([a-zX\*]*?)
                seti(?:C|c(?!lov)[a-z]*[A-Z]?))|
            (?#
                eighth branch matches most everything else, excluding \volcite,
                \mcite, \citereset and \citestyle
                syntax is:
                \cite[prenote][postnote]{key}
            )
            (?:(?P<prefix8>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                (?:[\.\*\?]){0,2}(?!teser|elyts)(?P<fancy_cite>[a-zX\*]*?)
                eti(?:C|c(?!lov|m\\)[a-z]*[A-Z]?))|
            (?#
                ninth branch matches apacite commands
            )
            (?:(?P<prefix9>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?
                (?:>[^<]*<)?(?:(?:PN)?(?:raey|rohtua)|PN|A)?etic)
        )\\""", re.X)

def match(rex, str):
    m = rex.match(str)
    if m:
        return m.group(0)
    else:
        return None

# recursively search all linked tex files to find all
# included bibliography tags in the document and extract
# the absolute filepaths of the bib files
def find_bib_files(rootdir, src, bibfiles):
    if src[-4:].lower() != ".tex":
        src = src + ".tex"

    file_path = os.path.normpath(os.path.join(rootdir,src))
    print("Searching file: " + repr(file_path))
    # See latex_ref_completion.py for why the following is wrong:
    #dir_name = os.path.dirname(file_path)

    # read src file and extract all bibliography tags
    try:
        src_file = codecs.open(file_path, "r", 'UTF-8')
    except IOError:
        sublime.status_message("LaTeXTools WARNING: cannot open included file " + file_path)
        print ("WARNING! I can't find it! Check your \\include's and \\input's.")
        return

    src_content = re.sub("%.*","",src_file.read())
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

    bibtags =  re.findall(r'\\bibliography\{[^\}]+\}', src_content)
    bibtags += re.findall(r'\\addbibresource\{[^\}]+.bib\}', src_content)

    # extract absolute filepath for each bib file
    for tag in bibtags:
        bfiles = re.search(r'\{([^\}]+)', tag).group(1).split(',')
        for bf in bfiles:
            if bf[-4:].lower() != '.bib':
                bf = bf + '.bib'
            # We join with rootdir, the dir of the master file
            candidate_file = os.path.normpath(os.path.join(rootdir,bf))
            # if the file doesn't exist, search the default tex paths
            if not os.path.exists(candidate_file):
                candidate_file = kpsewhich(bf, 'mlbib')

            if candidate_file is not None and os.path.exists(candidate_file):
                bibfiles.append(candidate_file)

    # search through input tex files recursively
    for f in re.findall(r'\\(?:input|include)\{[^\}]+\}',src_content):
        input_f = re.search(r'\{([^\}]+)', f).group(1)
        find_bib_files(rootdir, input_f, bibfiles)

def get_cite_completions(view, point, autocompleting=False):
    line = view.substr(sublime.Region(view.line(point).a, point))
    # print line

    # Reverse, to simulate having the regex
    # match backwards (cool trick jps btw!)
    line = line[::-1]
    #print line

    # Check the first location looks like a cite_, but backward
    # NOTE: use lazy match for the fancy cite part!!!
    # NOTE2: restrict what to match for fancy cite
    rex = OLD_STYLE_CITE_REGEX
    expr = match(rex, line)

    # See first if we have a cite_ trigger
    if expr:
        # Do not match on plain "cite[a-zX*]*?" when autocompleting,
        # in case the user is typing something else
        if autocompleting and re.match(r"[a-zX*]*etic\\?", expr):
            raise UnrecognizedCiteFormatError()
        # Return the completions
        prefix, fancy_cite = rex.match(expr).groups()
        preformatted = False
        if prefix:
            prefix = prefix[::-1]  # reverse
            prefix = prefix[1:]  # chop off _
        else:
            prefix = ""  # because this could be a None, not ""
        if fancy_cite:
            fancy_cite = fancy_cite[::-1]
            # fancy_cite = fancy_cite[1:] # no need to chop off?
            if fancy_cite[-1] == "X":
                fancy_cite = fancy_cite[:-1] + "*"
        else:
            fancy_cite = ""  # again just in case
        # print prefix, fancy_cite

    # Otherwise, see if we have a preformatted \cite{}
    else:
        rex = NEW_STYLE_CITE_REGEX
        expr = match(rex, line)

        if not expr:
            raise UnrecognizedCiteFormatError()

        preformatted = True
        m = rex.match(expr)
        prefix =   (m.group('prefix1') or
                    m.group('prefix2') or
                    m.group('prefix3') or
                    m.group('prefix4') or
                    m.group('prefix5') or
                    m.group('prefix6') or
                    m.group('prefix7') or
                    m.group('prefix8') or
                    m.group('prefix9'))
        if prefix:
            prefix = prefix[::-1]
        else:
            prefix = ""
        fancy_cite = m.group('fancy_cite')
        if fancy_cite:
            fancy_cite = fancy_cite[::-1]
            if fancy_cite[-1] == "X":
                fancy_cite = fancy_cite[:-1] + "*"
        else:
            fancy_cite = ""
        # print prefix, fancy_cite

    # if the key is an optional parameter, ensure we close the optional parameter
    post_brace = "}" if not re.match(r'(?:[^\[\],]*)\[', expr) else ']'

    # Reverse back expr
    expr = expr[::-1]

    if not preformatted:
        # Replace cite_blah with \cite{blah
        pre_snippet = "\cite" + fancy_cite + "{"
        # The "latex_tools_replace" command is defined in latex_ref_cite_completions.py
        view.run_command("latex_tools_replace", {"a": point-len(expr), "b": point, "replacement": pre_snippet + prefix})        
        # save prefix begin and endpoints points
        new_point_a = point - len(expr) + len(pre_snippet)
        new_point_b = new_point_a + len(prefix)

    else:
        # Don't include post_brace if it's already present
        suffix = view.substr(sublime.Region(point, point + len(post_brace)))
        new_point_a = point - len(prefix)
        new_point_b = point
        if post_brace == suffix:
            post_brace = ""

    #### GET COMPLETIONS HERE #####

    root = getTeXRoot.get_tex_root(view)

    if root is None:
        # This is an unnamed, unsaved file
        # FIXME: should probably search the buffer instead of giving up
        raise NoBibFilesError()

    print ("TEX root: " + repr(root))
    bib_files = []
    find_bib_files(os.path.dirname(root), root, bib_files)
    # remove duplicate bib files
    bib_files = list(set(bib_files))
    print ("Bib files found: ")
    print (repr(bib_files))

    if not bib_files:
        # sublime.error_message("No bib files found!") # here we can!
        raise NoBibFilesError()

    bib_files = ([x.strip() for x in bib_files])

    print ("Files:")
    print (repr(bib_files))

    from pybtex.database.input import bibtex

    completions = []
    parser = bibtex.Parser()

    for bibfname in bib_files:
        try:
            bibf = codecs.open(bibfname,'r','UTF-8', 'ignore')  # 'ignore' to be safe
        except IOError:
            print ("Cannot open bibliography file %s !" % (bibfname,))
            sublime.status_message("Cannot open bibliography file %s !" % (bibfname,))
            continue
        else:
            try:
                bib_data = parser.parse_stream(bibf)
            except pybtex.scanner.PybtexSyntaxError as e:
                message = 'Error while processing bibliography file {}! {}'.format(
                    bibfname, e
                )
                print (message)
                raise BibParsingError(bibfname, e)
            finally:
                bibf.close()

            print ('Loaded %d bibitems' % (len(bib_data.entries)))

            entries = []

            for key in bib_data.entries:
                entry = bib_data.entries[key]
                if entry.type == 'xdata' or entry.type == 'comment' or entry.type == 'string':
                    continue

                entries.append(EntryWrapper(entry))

        print ( "Found %d total bib entries" % (len(entries),) )

        # completions object
        completions += entries


    #### END COMPLETIONS HERE ####

    return completions, prefix, post_brace, new_point_a, new_point_b

if _ST3:
    def _get_people_long(people):
        return u' and '.join([str(x) for x in people])
else:
    def _get_people_long(people):
        return u' and '.join([unicode(x) for x in people])

def _get_people_short(people):
    if len(people) <= 2:
        return u' & '.join([u' '.join(x.last()) for x in people])
    else:
        return u' '.join(people[0].last()) + u', et al.'

# wrapper to implement a dict-like interface for bibliographic entries
# returning formatted value, if it is available
class EntryWrapper(MutableMapping):
    def __init__(self, entry):
        self.entry = entry

    def __getitem__(self, key):
        if not key:
            return u'????'

        key = key.lower()
        result = None

        short = False
        if key.endswith('_short'):
            short = True
            key = key[:-6]

        if key == 'keyword':
            return self.entry.key

        if key in pybtex.database.Person.valid_roles:
            try:
                people = self.entry.persons[key]
                if short:
                    result = _get_people_short(people)
                else:
                    result = _get_people_long(people)
            except KeyError:
                if 'crossref' in self.entry.fields:
                    try:
                        people = self.entry.get_crossref().persons[key]
                        if short:
                            result = _get_people_short(people)
                        else:
                            result = _get_people_long(people)
                    except KeyError:
                        pass

                if not result and key == 'author':
                    if short:
                        result = self['editor_short']
                    else:
                        result = self['editor']

                if not result:
                    return u'????'
        elif key == 'translator':
            try:
                people = [pybtex.database.Person(name) for name in
                    split_name_list(self.entry.fields[key])]
                if short:
                    result = _get_people_short(people)
                else:
                    result = _get_people_long(people)
            except KeyError:
                return u'????'

        if not result:
            try:
                result = self.entry.fields[key]
            except KeyError:
                if key == 'year':
                    try:
                        date = self.entry.fields['date']
                        date_matcher = re.match(r'(\d{4})', date)
                        if date_matcher:
                            result = date_matcher.group(1)
                    except KeyError:
                        pass
                elif key == 'journal':
                    return self['journaltitle']

                if not result:
                    return u'????'

        if key == 'title' and short:
            sep = re.compile(":|\.|\?")
            result = sep.split(result)[0]
            if len(result) > 60:
                result = result[0:60] + '...'

        return remove_latex_commands(codecs.decode(result, 'latex'))

    def __delitem__(self, key):
        raise KeyError

    def __setitem__(self, key, value):
        raise KeyError

    def __iter__(self):
        return iter(self.entry)

    def __len__(self):
        return len(self.entry)


# Based on html_completions.py
# see also latex_ref_completions.py
#
# It expands citations; activated by 
# cite<tab>
# citep<tab> and friends
#
# Furthermore, you can "pre-filter" the completions: e.g. use
#
# cite_sec
#
# to select all citation keywords starting with "sec". 
#
# There is only one problem: if you have a keyword "sec:intro", for instance,
# doing "cite_intro:" will find it correctly, but when you insert it, this will be done
# right after the ":", so the "cite_intro:" won't go away. The problem is that ":" is a
# word boundary. Then again, TextMate has similar limitations :-)
#
# There is also another problem: * is also a word boundary :-( So, use e.g. citeX if
# what you want is \cite*{...}; the plugin handles the substitution

class LatexCiteCompletions(sublime_plugin.EventListener):

    def on_query_completions(self, view, prefix, locations):
        # Only trigger within LaTeX
        if not view.match_selector(locations[0],
                "text.tex.latex"):
            return []

        point = locations[0]

        try:
            completions, prefix, post_brace, new_point_a, new_point_b = get_cite_completions(view, point, autocompleting=True)
        except UnrecognizedCiteFormatError:
            return []
        except NoBibFilesError:
            sublime.status_message("No bib files found!")
            return []
        except BibParsingError as e:
            sublime.error_message("Bibliography {} is broken! {}".format(
                e.filename, e
            ))            
            return []

        if prefix:
            completions = [comp for comp in completions if prefix.lower() in "%s %s" % (comp[0].lower(), comp[1].lower())]
            prefix += " "

        # get preferences for formating of autocomplete entries
        s = sublime.load_settings("LaTeXTools.sublime-settings")
        cite_autocomplete_format = s.get("cite_autocomplete_format", "{keyword}: {title}")

        formatter = Formatter()
        r = [(prefix + formatter.vformat(cite_autocomplete_format, (), completion), 
            completion['keyword'] + post_brace) for completion in completions]

        return r


class LatexCiteCommand(sublime_plugin.TextCommand):

    # Remember that this gets passed an edit object
    def run(self, edit):
        # get view and location of first selection, which we expect to be just the cursor position
        view = self.view
        point = view.sel()[0].b
        print (point)
        # Only trigger within LaTeX
        # Note using score_selector rather than match_selector
        if not view.score_selector(point,
                "text.tex.latex"):
            return

        try:
            completions, prefix, post_brace, new_point_a, new_point_b = get_cite_completions(view, point)
        except UnrecognizedCiteFormatError:
            sublime.error_message("Not a recognized format for citation completion")
            return
        except NoBibFilesError:
            sublime.error_message("No bib files found!")
            return
        except BibParsingError as e:
            sublime.error_message("Bibliography {} is broken! {}".format(
                e.filename, e
            ))
            return

        # filter against keyword, title, or author
        if prefix:
            completions = [comp for comp in completions if prefix.lower() in "%s %s %s" \
                                                    % (comp[0].lower(), comp[1].lower(), comp[2].lower())]

        # Note we now generate citation on the fly. Less copying of vectors! Win!
        def on_done(i):
            print ("latex_cite_completion called with index %d" % (i,) )

            # Allow user to cancel
            if i<0:
                return

            cite = completions[i]['keyword'] + post_brace

            #print("DEBUG: types of new_point_a and new_point_b are " + repr(type(new_point_a)) + " and " + repr(type(new_point_b)))
            # print "selected %s:%s by %s" % completions[i][0:3]
            # Replace cite expression with citation
            # the "latex_tools_replace" command is defined in latex_ref_cite_completions.py
            view.run_command("latex_tools_replace", {"a": new_point_a, "b": new_point_b, "replacement": cite})
            # Unselect the replaced region and leave the caret at the end
            caret = view.sel()[0].b
            view.sel().subtract(view.sel()[0])
            view.sel().add(sublime.Region(caret, caret))

        # get preferences for formating of quick panel
        s = sublime.load_settings("LaTeXTools.sublime-settings")
        if _ST3:
            cite_panel_format = s.get("cite_panel_format", ["{title} ({keyword})", "{author}"])
        else:
            cite_panel_format = map(unicode, s.get("cite_panel_format", ["{title} ({keyword})", "{author}"]))

        # show quick
        formatter = Formatter()
        view.window().show_quick_panel([[formatter.vformat(str, (), completion) for str in cite_panel_format] \
                                        for completion in completions], on_done)
