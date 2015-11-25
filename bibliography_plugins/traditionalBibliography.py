from latextools_plugin import LaTeXToolsPlugin

from kpsewhich import kpsewhich
from latextools_utils.subfiles import walk_subfiles

import pybtex
from pybtex.bibtex.utils import split_name_list
from pybtex.database.input import bibtex

import latex_chars

import codecs
from collections import Mapping

import re
import os

import sublime

# LaTeX -> Unicode decoder
latex_chars.register()

if sublime.version() < '3000':
    def _get_people_long(people):
        return u' and '.join([unicode(x) for x in people])
else:
    def _get_people_long(people):
        return u' and '.join([str(x) for x in people])

def _get_people_short(people):
    if len(people) <= 2:
        return u' & '.join([u' '.join(x.last()) for x in people])
    else:
        return u' '.join(people[0].last()) + u', et al.'

def remove_latex_commands(s):
    u'''
    Simple function to remove any LaTeX commands or brackets from the string,
    replacing it with its contents.

    >>> remove_latex_commands(u'A Marxist Schelling')
    u'A Marxist Schelling'

    >>> remove_latex_commands(u'A {Marxist} Schelling')
    u'A Marxist Schelling'

    >>> remove_latex_commands(ur'\\textgerman{Ein marxistischer Schelling --- Zu Ernst Blochs spekulativen Materialismus}')
    u'Ein marxistischer Schelling --- Zu Ernst Blochs spekulativen Materialismus'

    >>> remove_latex_commands(ur'A \\emph{Marxist} Schelling')
    u'A Marxist Schelling'

    >>> remove_latex_commands(ur'\\textgerman{Ein marxistischer Schelling --- Zu \\emph{Ernst Blochs} spekulativen Materialismus}')
    u'Ein marxistischer Schelling --- Zu Ernst Blochs spekulativen Materialismus'

    >>> remove_latex_commands(ur'\\textgerman{Ein marxistischer Schelling --- Zu \\emph{Ernst {Blochs}} spekulativen Materialismus}')
    u'Ein marxistischer Schelling --- Zu Ernst Blochs spekulativen Materialismus'

    >>> remove_latex_commands(ur'\\noindent Some text')
    u'Some text'
    '''
    chars = []
    FOUND_SLASH = False

    for c in s:
        if c == '{':
            # i.e., we are entering the contents of the command
            if FOUND_SLASH:
                FOUND_SLASH = False
        elif c == '}':
            pass
        elif c == '\\':
            FOUND_SLASH = True
        elif not FOUND_SLASH:
            chars.append(c)
        elif c.isspace():
            FOUND_SLASH = False

    return ''.join(chars)

# wrapper to implement a dict-like interface for bibliographic entries
# returning formatted value, if it is available
class EntryWrapper(Mapping):
    def __init__(self, entry):
        self.entry = entry

    def __getitem__(self, key):
        if not key:
            return u''

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
                    return u''
        elif key == 'translator':
            try:
                people = [pybtex.database.Person(name) for name in
                          split_name_list(self.entry.fields[key])]
                if short:
                    result = _get_people_short(people)
                else:
                    result = _get_people_long(people)
            except KeyError:
                return u''

        if not result:
            try:
                result = self.entry.fields[key]
            except KeyError:
                return u''

        return remove_latex_commands(codecs.decode(result, 'latex'))

    def __iter__(self):
        return iter(self.entry)

    def __len__(self):
        return len(self.entry)

class TraditionalBibliographyPlugin(LaTeXToolsPlugin):
    def find_bibliography_files(self, root_file):
        bib_files = []

        rootdir = os.path.dirname(root_file)

        for content in walk_subfiles(rootdir, root_file):
            bibtags =  re.findall(r'\\bibliography\{([^\}]+)\}', content)
            bibtags += re.findall(r'\\addbibresource(?:\[[^\]]*\])?\{([^\}]+)\.bib\}', content)
            bibtags += re.findall(r'\\addglobalbib(?:\[[^\]]*\])?\{([^\}]+)\.bib\}', content)
            bibtags += re.findall(r'\\addsectionbib(?:\[[^\]]*\])?\{([^\}]+)\.bib\}', content)
            bibtags += re.findall(r'\\begin\{refsection\}\[([^\]]+)\]', content)

            # extract absolute filepath for each bib file
            for tag in bibtags:
                bfiles = tag.split(',')
                for bf in bfiles:
                    if bf[-4:].lower() != '.bib':
                        bf = bf + '.bib'
                    # We join with rootdir, the dir of the master file
                    candidate_file = os.path.normpath(os.path.join(rootdir, bf))
                    # if the file doesn't exist, search the default tex paths
                    if not os.path.exists(candidate_file):
                        candidate_file = kpsewhich(bf, 'mlbib')

                    if candidate_file is not None and os.path.exists(candidate_file):
                        bib_files.append(candidate_file)
        return bib_files

    def get_entries(self, *bib_files):
        entries = []
        parser = bibtex.Parser()
        for bibfname in bib_files:
            try:
                bibf = codecs.open(bibfname, 'r', 'UTF-8', 'ignore')  # 'ignore' to be safe
            except IOError:
                print("Cannot open bibliography file %s !" % (bibfname,))
                sublime.status_message("Cannot open bibliography file %s !" % (bibfname,))
                continue
            else:
                bib_data = parser.parse_stream(bibf)
                bibf.close()

                print ('Loaded %d bibitems' % (len(bib_data.entries)))

                for key in bib_data.entries:
                    entry = bib_data.entries[key]
                    if entry.type == 'xdata' or entry.type == 'comment' or entry.type == 'string':
                        continue

                    entries.append(EntryWrapper(entry))

            print("Found %d total bib entries" % (len(entries),))

        return entries

    def on_insert_citation(self, keyword):
        print('Inserted {0}'.format(keyword))
