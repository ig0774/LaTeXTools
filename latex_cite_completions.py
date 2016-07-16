'''
This module implements the cite-completion behaviour, largely by relying on
implementations registered with latextools_plugin and configured using the
`bibliograph_plugins` configuration key.

At present, there are two supported methods on custom plugins.

`find_bibliography_files`:
    This method should take a single argument, the full path the to root
    document and return a list of absolute filenames for the various
    bibliography files to be used. This list will be passed to `get_entries`.

`get_entries`:
    This method should take a sequence of bib_files and return a sequence of
    Mapping-like objects where the key corresponds to a Bib(La)TeX key and
    returns the matching value. We provide default fallbacks for any of the
    quick panel formatting options that might not be automatically mapped to
    a field, e.g., `author_short`, etc. or to deal with missing data, e.g.
    entries that have no `journal` but use the `journaltitle` field. Plugins
    can override this behaviour, however, by explicitly setting a value for
    whatever key they like.
'''
# ST2/ST3 compat
from __future__ import print_function
import sublime

import os
import sys

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    import getTeXRoot
    from latex_fill_all import FillAllHelper
    from latextools_utils import get_setting
    import latextools_plugin
    from latextools_utils import bibformat

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")

    strbase = basestring
else:
    _ST3 = True
    from . import getTeXRoot
    from .latex_fill_all import FillAllHelper
    from .latextools_utils import get_setting
    from . import latextools_plugin
    from .latextools_utils import bibformat

    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

    strbase = str

import re
from string import Formatter
import traceback

class UnrecognizedCiteFormatError(Exception): pass
class NoBibFilesError(Exception): pass

class BibParsingError(Exception):
    def __init__(self, filename="", message=""):
        super(BibParsingError, self).__init__(message)
        self.filename = filename

class BibPluginError(Exception): pass

OLD_STYLE_CITE_REGEX = re.compile(r"([^_]*_)?\*?([a-z]*?)etic\\")
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
#           (?:[A-Z]?[a-z]*c)|C)ites(?!style)
#           (?:\([^)]*\)){0,2}
#           (?:(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?(?:\}(?=.*?\{))?){1,}|
#       (?#
#           eighth branch matches most everything else, excluding \volcite,
#           \mcite, \citereset and \citestyle
#           syntax is:
#           \cite[<prenote>][<postnote>]{key}
#       )
#       (?:(?!(?:p|P|f|ft|s|S|t|T|a|A)?volcite|mcite)
#           (?:[A-Z]?[a-z]*c)|C)ite(?!reset\*?|style)([a-zX*]*?)
#           ([.*?]){0,2}(?:\[[^\]]*\]){0,2}\{(?:(?:[^{},]*,)*)?|
#       (?#
#           ninth branch matches apacite commands
#           syntax is:
#           \citeA<prenote>[postnote]{key}
#       )
#       (?:mask)?(?:full|short)cite
#           (?:(?:author|year)(?:NP)?|NP|A)?
#           (?:<[^>]*>)?(?:\[[^\]]*\])?\{(?:(?:[^{},]*,)*)?)$
NEW_STYLE_CITE_REGEX = re.compile(
    r"""(?:
            (?:(?P<prefix1>[^\[\],]*)(?:,[^\[\],]*)*\[\}[^\{]*\{
                \*?etouq(?:kcolb|txet)(?:ngierof|nehpyh|(?<=kcolb)dirbyh))|
            (?:(?P<prefix2>[^\[\],]*)(?:,[^\[\],]*)*\[\*?etouq(?:kcolb|txet))|
            (?:(?P<prefix3>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}\}[^\{]*\{
                \*?etouqc(?:kcolb|txet)(?:ngierof|nehpyh|(?<=kcolb)dirbyh))|
            (?:(?P<prefix4>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                \*?etouqc(?:kcolb|txet))|
            (?:(?P<prefix5>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?
                eticlov(?:p|P|f|ft|s|S|t|T|a|A)?)|
            (?:(?P<prefix6>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?
                (?:\}[^\{}]*\{(?:\][^\[]*\[)?\}[^\{}]*\{(?:\][^\[]*\[)?)*
                (?:\)[^(]*\(){0,2}
                seticlov(?:p|P|f|ft|s|S|t|T|a|A)?)|
            (?:(?P<prefix7>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                (?:\}[^\}]*\{(?:\][^\[]*\[){0,2})*
                (?:[\.\*\?]){0,2}(?:\)[^(]*\(){0,2}
                seti(?:C|c(?!lov)[a-z]*[A-Z]?))|
            (?:(?P<prefix8>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[){0,2}
                (?:[\.\*\?]){0,2}(?!\*?teser|elyts)(?P<fancy_cite>[a-zX\*]*?)
                eti(?:C|c(?!lov|m\\)[a-z]*[A-Z]?))|
            (?:(?P<prefix9>[^{},]*)(?:,[^{},]*)*\{(?:\][^\[]*\[)?
                (?:>[^<]*<)?(?:(?:PN)?(?:raey|rohtua)|PN|A)?etic
                (?:lluf|trohs)?(?:ksam)?)
        )\\""", re.X)

def match(rex, str):
    m = rex.match(str)
    if m:
        return m.group(0)
    else:
        return None

def run_plugin_command(command, *args, **kwargs):
    '''
    This function is intended to run a command against a user-configurable list
    of bibliography plugins set using the `bibliography` setting.

    Parameters:
        `command`: a string representing the command to invoke, which should
            generally be the name of a function to be called on the plugin
                class.
        `*args`: the args to pass to the function
        `**kwargs`: the keyword args to pass to the function

    Additionally, the following keyword parameters can be specified to control
    how this function works:
        `stop_on_first`: if True (default), no more attempts will be made to
            run the command after the first plugin that returns a non-None
            result
        `expect_result`: if True (default), a BibPluginError will be raised if
            no plugin returns a non-None result

    Example:
        run_plugin_command('get_entries', *bib_files)
        This will attempt to invoke the `get_entries` method of any configured
        plugin, passing in the discovered bib_files, and returning the result.

    The general assumption of this function is that we only care about the
    first valid result returned from a plugin and that plugins that should not
    handle a request will either not implement the method or implement a
    version of the method which raises a NotImplementedError if that plugin
    should not handle the current situation.
    '''
    stop_on_first = kwargs.pop('stop_on_first', True)
    expect_result = kwargs.pop('expect_result', True)

    def _run_command(plugin_name):
        plugin = None
        try:
            plugin = latextools_plugin.get_plugin(plugin_name)
        except latextools_plugin.NoSuchPluginException:
            pass

        if not plugin:
            error_message = 'Could not find bibliography plugin named {0}. Please ensure your LaTeXTools.sublime-settings is configured correctly.'.format(
                plugin_name)
            print(error_message)
            raise BibPluginError(error_message)

        # instantiate plugin
        try:
            plugin = plugin()
        except:
            error_message = 'Could not instantiate {0}. {0} must have a no-args __init__ method'.format(
                type(plugin).__name__,
            )

            print(error_message)
            raise BibPluginError(error_message)

        try:
            result = getattr(plugin, command)(*args, **kwargs)
        except TypeError as e:
            if "'{0}()'".format(command) in str(e):
                error_message = '{1} is not properly implemented by {0}.'.format(
                    type(plugin).__name__,
                    command
                )

                print(error_message)
                raise BibPluginError(error_message)
            else:
                reraise(*sys.exc_info())
        except AttributeError as e:
            if "'{0}'".format(command) in str(e):
                error_message = '{0} does not implement `{1}`'.format(
                    type(plugin).__name__,
                    command
                )

                print(error_message)
                raise BibPluginError(error_message)
            else:
                reraise(*sys.exc_info())
        except NotImplementedError:
            return None

        return result

    plugins = get_setting('bibliography', ['traditional'])
    if not plugins:
        print('bibliography setting is blank. Loading traditional plugin.')
        plugins = 'traditional'

    result = None
    if isinstance(plugins, strbase):
        if not plugins.endswith('_bibliography'):
            plugins = '{0}_bibliography'.format(plugins)
        result = _run_command(plugins)
    else:
        for plugin_name in plugins:
            if not plugin_name.endswith('_bibliography'):
                plugin_name = '{0}_bibliography'.format(plugin_name)
            try:
                result = _run_command(plugin_name)
            except BibPluginError:
                continue
            if stop_on_first and result is not None:
                break

    if expect_result and result is None:
        raise BibPluginError("Could not find a plugin to handle '{0}'. See the console for more details".format(command))
    return result


def get_cite_completions(view):
    #### GET COMPLETIONS HERE #####

    root = getTeXRoot.get_tex_root(view)

    if root is None:
        # This is an unnamed, unsaved file
        # FIXME: should probably search the buffer instead of giving up
        raise NoBibFilesError()

    print(u"TEX root: " + repr(root))
    bib_files = []
    find_bib_files(os.path.dirname(root), root, bib_files)
    # remove duplicate bib files
    bib_files = list(set(bib_files))
    print("Bib files found: ")
    print(repr(bib_files))

    if not bib_files:
        # sublime.error_message("No bib files found!") # here we can!
        raise NoBibFilesError()

    bib_files = ([x.strip() for x in bib_files])

    completions = run_plugin_command('get_entries', *bib_files)

    #### END COMPLETIONS HERE ####

    completions = [CompletionWrapper(completion) for completion in completions]

    return completions

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
class CiteFillAllHelper(FillAllHelper):

    def get_auto_completions(self, view, prefix, line):
        # Reverse, to simulate having the regex
        # match backwards (cool trick jps btw!)
        line = line[::-1]

        # Check the first location looks like a cite_, but backward
        old_style = OLD_STYLE_CITE_REGEX.match(line)

        # Do not match on plain "cite[a-zX*]*?" when autocompleting,
        # in case the user is typing something else
        if old_style and not prefix:
            return []

        try:
            completions = get_cite_completions(view)
        except UnrecognizedCiteFormatError:
            return []
        except NoBibFilesError:
            print("No bib files found!")
            sublime.status_message("No bib files found!")
            return []
        except BibParsingError as e:
            message = "Error occurred parsing {0}. {1}.".format(
                e.filename, e.message
            )
            print(message)
            traceback.print_exc()

            sublime.status_message(message)
            return []

        if prefix:
            lower_prefix = prefix.lower()
            completions = [
                c for c in completions
                if _is_prefix(lower_prefix, c)
            ]

        if len(completions) == 0:
            return []

        cite_autocomplete_format = get_setting(
            'cite_autocomplete_format',
            '{keyword}: {title}'
        )

        formatted_completions = []
        for completion in completions:
            try:
                formatted_completions.append((
                    completion["<autocomplete_formatted>"],
                    completion['keyword']
                ))
            except:
                formatted_completions.append((
                    bibformat.format_entry(
                        cite_autocomplete_format, completion
                    ),
                    completion['keyword']
                ))

        if old_style:
            return formatted_completions, '{'
        else:
            return formatted_completions

    def get_completions(self, view, prefix, line):
        try:
            completions = get_cite_completions(view)
        except UnrecognizedCiteFormatError:
            sublime.error_message(
                "Unrecognized format for citation completion"
            )
            return
        except NoBibFilesError:
            sublime.error_message("No bib files found!")
            return
        except BibParsingError as e:
            traceback.print_exc()
            sublime.error_message(
                "Error occurred parsing {0}. {1}.".format(
                    e.filename, e.message
                )
            )
            return

        if prefix:
            lower_prefix = prefix.lower()
            completions = [
                c for c in completions
                if _is_prefix(lower_prefix, c)
            ]

        completions_length = len(completions)
        if completions_length == 0:
            return
        elif completions_length == 1:
            return [completions[0]['keyword']]

        cite_panel_format = get_setting(
            'cite_panel_format',
            ["{title} ({keyword})", "{author}"]
        )

        formatted_completions = []
        result_completions = []
        for completion in completions:
            try:
                formatted_completions.append(completion["<panel_formatted>"])
            except:
                formatted_completions.append(
                    [
                        bibformat.format_entry(s, completion)
                        for s in cite_panel_format
                    ]
                )
            result_completions.append(completion['keyword'])

        return formatted_completions, result_completions

    def matches_line(self, line):
        return bool(
            OLD_STYLE_CITE_REGEX.match(line) or
            NEW_STYLE_CITE_REGEX.match(line)
        )

    def is_enabled(self):
        return get_setting('cite_auto_trigger', True)

    def supports_fancy_prefix(self):
        return True


def _is_prefix(lower_prefix, entry):
    try:
        return lower_prefix in entry["<prefix_match>"]
    except:
        return lower_prefix in bibformat.create_prefix_match_str(entry)


def plugin_loaded():
    # load plugins from the bibliography_plugins dir of LaTeXTools if it exists
    # this allows us to have pre-packaged plugins that won't require any user
    # setup
    os_path = os.path
    latextools_plugin.add_plugin_path(
        os_path.join(os_path.dirname(__file__), 'bibliography_plugins'))

# ensure plugin_loaded() called on ST2
if not _ST3:
    plugin_loaded()
