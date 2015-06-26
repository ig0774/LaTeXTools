# coding=utf-8

from __future__ import print_function

import sublime
import sublime_plugin

from collections import namedtuple

import re
import sys

if sys.version_info > (3, 0):
    strbase = str
    unicode = str
else:
    strbase = basestring

# list of known BibLaTeX fields of the type `list (name)`
NAME_FIELDS = set((
    'author',
    'bookauthor',
    'commentator',
    'editor',
    'editora',
    'editorb',
    'editorc',
    'foreword',
    'holder',
    'introduction',
    'shortauthor',
    'shorteditor',
    'translator',
    'sortname',
    'namea',
    'nameb',
    'namec'
))

# Regex to recognise if we are in a name field
#
# I've tried to simply the comprehensibility of the backwards regexes used by
# constructing them here
#
# VALUE_REGEX is a common suffix to hand the `= {<value>,<value>}` part
VALUE_REGEX = r'[\s~]*(?P<ENTRIES>(?:[\s~]*dna[\s~]+.+)+)?[\s~]*(?P<OPEN>\{)?(?P<EQUALS>\s*=\s*)?'

ON_NAME_FIELD_REGEX = re.compile(
    VALUE_REGEX + r'(?:' + r'|'.join((s[::-1] for s in NAME_FIELDS)) + r')' + r'\b',
    re.IGNORECASE | re.UNICODE
)

def is_bib_file(view):
    return view.match_selector(0, 'text.bibtex') or is_biblatex(view)

def is_biblatex(view):
    return view.match_selector(0, 'text.biblatex')

def get_text_to_cursor(view):
    cursor = view.sel()[0].b
    current_region = sublime.Region(0, cursor)
    return view.substr(current_region)

def split_tex_string(string, maxsplit=-1, sep=None):
    '''
    A variation of string.split() to support tex strings

    In particular, ignores text in brackets, no matter how deeply nested and
    defaults to breaking on any space char or ~.
    '''

    if sep is None:
        # tilde == non-breaking space
        sep = r'(?u)[\s~]+'
    sep_re = re.compile(sep)

    result = []

    # track ignore separators in braces
    brace_level = 0
    # calculate once
    string_len = len(string)
    word_start = 0
    splits = 0

    for pos, c in enumerate(string):
        if c == '{':
            brace_level += 1
        elif c == '}':
            brace_level -= 1
        elif brace_level == 0 and pos > 0:
            matcher = sep_re.match(string[pos:])
            if matcher:
                sep_len = len(matcher.group())
                if pos + sep_len <= string_len:
                    result.append(string[word_start:pos])
                    word_start = pos + sep_len

                    splits += 1
                    if splits == maxsplit:
                        break

    if word_start < string_len:
        result.append(string[word_start:])

    return [part.strip() for part in result if part]

def tokenize_list(list_str):
    u'''
    >>> tokenize_list('Chemicals and Entrails')
    ['Chemicals', 'Entrails']

    >>> tokenize_list('{Harman and Feather Corporation}')
    ['{Harman and Feather Corporation}']

    >>> tokenize_list('Harman { and } Feather Corporation')
    ['Harman { and } Feather Corporation']

    >>> tokenize_list('Harman {and} Feather Corporation')
    ['Harman {and} Feather Corporation']

    >>> tokenize_list('Chemicals~and~Entrails')
    ['Chemicals', 'Entrails']

    >>> tokenize_list('Chemicals and')
    ['Chemicals']
    '''
    return split_tex_string(list_str, sep=r'(?iu)[\s~]+and(?:[\s~]+|$)')

# namedtuple so results are a little more comprehensible
NameResult = namedtuple('NameResult', ['first', 'middle', 'prefix', 'last', 'generation'])

def tokenize_name(name_str):
    u'''
    Takes a string representing a name and returns a NameResult breaking that
    string into its component parts, as defined in the LaTeX book and BibTeXing.

    Note that while this should preserve non-breaking spaces within a given name
    component, preserving them where they act as a separator between two name
    components require a more complex data structure than we use here.

    >>> tokenize_name('Coddlington, Simon')
    NameResult(first='Simon', middle='', prefix='', last='Coddlington', generation='')

    >>> tokenize_name('Simon Coddlington')
    NameResult(first='Simon', middle='', prefix='', last='Coddlington', generation='')

    >>> tokenize_name('Simon~Coddlington')
    NameResult(first='Simon', middle='', prefix='', last='Coddlington', generation='')

    >>> tokenize_name('Simon P. Coddlington')
    NameResult(first='Simon', middle='P.', prefix='', last='Coddlington', generation='')

    >>> tokenize_name('Coddlington, Simon P.')
    NameResult(first='Simon', middle='P.', prefix='', last='Coddlington', generation='')

    >>> tokenize_name('Coddlington, Simon~P.')
    NameResult(first='Simon', middle='P.', prefix='', last='Coddlington', generation='')


    >>> tokenize_name('Willard van Orman Quine')
    NameResult(first='Willard', middle='van Orman', prefix='', last='Quine', generation='')

    >>> tokenize_name('Quine, Willard van Orman')
    NameResult(first='Willard', middle='van Orman', prefix='', last='Quine', generation='')

    >>> tokenize_name('Augustine')
    NameResult(first='Augustine', middle='', prefix='', last='', generation='')

    >>> tokenize_name('Jean-Paul Sartre')
    NameResult(first='Jean-Paul', middle='', prefix='', last='Sartre', generation='')

    >>> tokenize_name('Sartre, Jean-Paul')
    NameResult(first='Jean-Paul', middle='', prefix='', last='Sartre', generation='')

    >>> tokenize_name('Charles Louis Xavier Joseph de la Vall{\\\'e}e Poussin')
    NameResult(first='Charles', middle="Louis Xavier Joseph de la Vall{'e}e", prefix='', last='Poussin', generation='')

    >>> tokenize_name(u'Charles Louis Xavier Joseph de la Vallée Poussin')
    NameResult(first=u'Charles', middle=u'Louis Xavier Joseph de la Vall\\xe9e', prefix='', last=u'Poussin', generation='')

    >>> tokenize_name('James van Houten')
    NameResult(first='James', middle='', prefix='van', last='Houten', generation='')

    >>> tokenize_name('van Houten, James')
    NameResult(first='James', middle='', prefix='van', last='Houten', generation='')

    >>> tokenize_name('Jones, Jr, James Earl')
    NameResult(first='James', middle='Earl', prefix='', last='Jones', generation='Jr')

    >>> tokenize_name('van auf der Rissen, Gloria')
    NameResult(first='Gloria', middle='', prefix='van auf der', last='Rissen', generation='')

    >>> tokenize_name('Gloria van auf der Rissen')
    NameResult(first='Gloria', middle='', prefix='van auf der', last='Rissen', generation='')

    >>> tokenize_name('Jean Charles-Gabriel')
    NameResult(first='Jean', middle='', prefix='', last='Charles-Gabriel', generation='')

    >>> tokenize_name('de la Vall{\\\'e}~Poussin, Jean Charles~Gabriel')
    NameResult(first='Jean', middle='Charles~Gabriel', prefix='de la', last="Vall{'e}~Poussin", generation='')
    '''
    def extract_middle_names(first):
        return split_tex_string(first, 1)

    def extract_name_prefix(last):
        names = split_tex_string(last, 1)
        if len(names) == 1:
            return names

        result = [names[0]]

        new_names = split_tex_string(names[1], 1)
        while len(new_names) > 1 and new_names[0].islower():
            result[0] = ' '.join((result[0], new_names[0]))
            names = new_names
            new_names = split_tex_string(names[1], 1)

        result.append(names[1])

        return result

    name_str = name_str.strip()

    parts = split_tex_string(name_str, sep=r',[\s~]*')
    if len(parts) == 1:
        # first last
        # reverse the string so split only selects the right-most instance of the token
        try:
            last, first = [part[::-1] for part in split_tex_string(parts[0][::-1], 1)]
        except ValueError:
            # we only have a single name
            return NameResult(
                parts[0],
                '', '', '', ''
            )

        # because of our splitting method, van, von, della, etc. may end up at the end of the first name field
        try:
            last_part_of_first, new_first = [part[::-1] for part in split_tex_string(first[::-1], 1)]
        except ValueError:
            # we only have one last name
            pass
        else:
            while last_part_of_first.islower():
                last = ' '.join((last_part_of_first, last))
                first = new_first
                try:
                    last_part_of_first, new_first = [part[::-1] for part in split_tex_string(first[::-1], 1)]
                except ValueError:
                    # we reached the end of the first name
                    break

        forenames = extract_middle_names(first)
        lastnames = extract_name_prefix(last)
        return NameResult(
            forenames[0],
            forenames[1] if len(forenames) > 1 else '',
            lastnames[0] if len(lastnames) > 1 else '',
            lastnames[1] if len(lastnames) > 1 else lastnames[0],
            ''
        )
    elif len(parts) == 2:
        # last, first
        last, first = parts
        forenames = extract_middle_names(first)
        lastnames = extract_name_prefix(last)
        return NameResult(
            forenames[0],
            forenames[1] if len(forenames) > 1 else '',
            lastnames[0] if len(lastnames) > 1 else '',
            lastnames[1] if len(lastnames) > 1 else lastnames[0],
            ''
        )
    elif len(parts) == 3:
        # last, generation, first
        last, generation, first = parts
        forenames = extract_middle_names(first)
        lastnames = extract_name_prefix(last)
        return NameResult(
            forenames[0],
            forenames[1] if len(forenames) > 1 else '',
            lastnames[0] if len(lastnames) > 1 else '',
            lastnames[1] if len(lastnames) > 1 else lastnames[0],
            generation
        )
    else:
        raise ValueError('Unrecognised name format for "{0}"'.format(name_str))

class Name(object):
    u'''
    Represents a BibLaTeX name entry. __str__ will return a name formatted in
    the preferred format

    >>> str(Name('Jean-Paul Sartre'))
    'Sartre, Jean-Paul'

    >>> str(Name('Simon~Coddlington'))
    'Coddlington, Simon'

    >>> str(Name('de la Vall{\\\'e}~Poussin, Jean Charles~Gabriel'))
    "de la Vall{\'e}~Poussin, Jean Charles~Gabriel"

    >>> str(Name('Gloria van auf der Rissen'))
    'van auf der Rissen, Gloria'
    '''
    def __init__(self, name_str):
        self.first = None
        self.middle = None
        self.prefix = None
        self.last = None
        self.generation = None

        self.first, self.middle, self.prefix, self.last, self.generation = \
            tokenize_name(name_str)

    def __unicode__(self):
        result = u' '.join((self.prefix, self.last)) if self.prefix else unicode(self.last)
        if self.generation:
            result = u', '.join((result, self.generation))
        result = u', '.join((result, self.first))
        if self.middle:
            result = u' '.join((result, self.middle))
        return result

    __str__ = __unicode__
    __repr__ = __unicode__

# builds the replacement string depending on the current context of the line
def _get_replacement(matcher, key):
    if not matcher.group('ENTRIES'):
        return u'{0}{1}{2}{3}'.format(
            u'' if matcher.group('EQUALS') else u'= ',
            u'' if matcher.group('OPEN') else u'{',
            key,
            u'' if matcher.group('OPEN') else u'}'
        )

    return '{0}{1}'.format(
        u',' if matcher.group('ENTRIES')[0] != u',' else u'',
        key
    )

NAME_FIELD_REGEX = re.compile(
    r'(?:^|[\s~]+)(?:' + r'|'.join(NAME_FIELDS) + ')\s*=\s*\{',
    re.IGNORECASE | re.UNICODE
)

def get_names_from_view(view):
    contents = view.substr(sublime.Region(0, view.size()))
    return get_names(contents)

def get_names(contents):
    u'''
    Work-horse function to extract all the names defined in the current bib file.

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         editor = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         translator = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {
    ...             Coddlington, Simon
    ...         },
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {
    ...             Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon
    ...         },
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon},
    ...         editor = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon and Gary Winchester},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon', u'Winchester, Gary']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Winchester, Gary},
    ...         editor = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon', u'Winchester, Gary']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Winchester, Gary},
    ...         editor = {Coddlington, Simon},
    ...         translator = {Winchester, Gary},
    ...         date = {2014/08/01}
    ...     }
    ... """)
    [u'Coddlington, Simon', u'Winchester, Gary']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon},
    ...         date = {2014/08/01}
    ...     }
    ...     @book {
    ...         title = {An Incredibly Long Disquisition on Absolutely Nothing at all Which I Ate For Breakfast Last Tuesday}
    ...     }
    ... """)
    [u'Coddlington, Simon']

    >>> get_names("""
    ...     @article {
    ...         title = {A Long Disquisition on Nothing},
    ...         author = {Coddlington, Simon and""")
    [u'Coddlington, Simon']
    '''
    names = []

    in_entry = False
    pos = 0
    contents_length = len(contents)

    while True:
        if not in_entry:
            matcher = re.search(NAME_FIELD_REGEX, contents[pos:])
            # no more `name =` fields
            if not matcher:
                break

            pos += matcher.end()
            in_entry = True
        else:
            chars = []

            bracket_depth = 1
            for c in contents[pos:]:
                if c == '}':
                    bracket_depth -= 1

                if bracket_depth == 0:
                    break

                if c == '{':
                    bracket_depth += 1

                chars.append(c)

            names.extend([unicode(Name(s)) for s in tokenize_list(u''.join(chars))])

            pos += len(chars)
            if pos >= contents_length:
                break
            in_entry = False

    return sorted(set(names))

class BiblatexNameCompletions(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        if not is_bib_file(view):
            return []

        current_line = get_text_to_cursor(view)[::-1]

        matcher = ON_NAME_FIELD_REGEX.match(current_line)
        if matcher:
            return ([(name, _get_replacement(matcher, name))
                    for name in get_names_from_view(view)],
                    sublime.INHIBIT_WORD_COMPLETIONS |
                    sublime.INHIBIT_EXPLICIT_COMPLETIONS)

        return []

if __name__ == '__main__':
    import doctest
    doctest.testmod()
