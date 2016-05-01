#!/usr/bin/env python
from __future__ import print_function

from pandocfilters import *


def remove_first_section_from_toc(key, value, f, meta):
    if (
        f == 'latex' and
        key == 'Header' and
        value[0] == 1
    ):
        label = value[1][0]
        heading = u' '.join([
            entry['c'] for entry in value[2] if entry['t'] == 'Str'
        ])
        return [Para([RawInline(
            "tex", u"\\section*{" + heading + u"}\label{" + label + u"}"
        )])]


def prepend_toc_to_body(key, value, f, meta):
    if (
        f == 'latex' and
        not prepend_toc_to_body.added_toc and
        key == 'Header' and
        value[0] == 2
    ):
        prepend_toc_to_body.added_toc = True
        return [Para([RawInline("tex", '\\tableofcontents')]), Header(*value)]

prepend_toc_to_body.added_toc = False

if __name__ == '__main__':
    toJSONFilters([
        remove_first_section_from_toc,
        prepend_toc_to_body
    ])
