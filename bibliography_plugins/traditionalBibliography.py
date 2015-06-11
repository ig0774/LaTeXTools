from latextools_plugin import LaTeXToolsPlugin

from latex_commands_grammar import remove_latex_commands

import pybtex
from pybtex.bibtex.utils import split_name_list
from pybtex.database.input import bibtex

import latex_chars

import codecs
from collections import Mapping
import re

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

# wrapper to implement a dict-like interface for bibliographic entries
# returning formatted value, if it is available
class EntryWrapper(Mapping):
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
            short_title = None
            try:
                short_title = self.entry.fields['shorttitle']
            except KeyError:
                pass

            if short_title:
                result = short_title
            else:
                sep = re.compile(":|\.|\?")
                result = sep.split(result)[0]
                if len(result) > 60:
                    result = result[0:60] + '...'

        return remove_latex_commands(codecs.decode(result, 'latex'))

    def __iter__(self):
        return iter(self.entry)

    def __len__(self):
        return len(self.entry)

class TraditionalBibliographyPlugin(LaTeXToolsPlugin):
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
        print('Inserted {}'.format(keyword))
