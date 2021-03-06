from __future__ import print_function
import sublime
import sublime_plugin
import re

if sublime.version() < '3000':
    _ST3 = False
    from getRegion import getRegion
    from latextools_utils import get_setting
else:
    _ST3 = True
    from .getRegion import getRegion
    from .latextools_utils import get_setting

SECTION_TYPES = ['part', 'chapter', 'section', 'subsection',
                 'subsubsection', 'paragraph', 'subparagraph']

SECTION_TYPES_PATTERNS = {
    'part': r'((?:add)?part)',
    'chapter': r'(chapter|addchap)',
    'section': r'(section|addsec)',
    'subsection': r'(subsection|addsubsec)',
    'subsubsection': r'(subsubsection|addsubsubsec)',
    'paragraph': r'paragraph',
    'subparagraph': r'subparagraph'
}


def get_begin_mark_pattern(sec_type):
    return r'\\' + SECTION_TYPES_PATTERNS[sec_type] + \
        r'\*?(?:\[.*\])?\{.*\}(?:\s*%\s\(fold\))?'


def get_end_mark_pattern(sec_type):
    return r'%\s*' + SECTION_TYPES_PATTERNS[sec_type] + r'.*\s*\(end\)'


# Find top level's mark name in this buffer
# return None if find failed
def find_top_level(view):
    top_level = None
    for i in SECTION_TYPES:
        regions = view.find_all(get_begin_mark_pattern(i))
        if len(regions) == 0:
            continue
        else:
            top_level = i
            break
    return top_level


# Retrive all segments by section types
# returned result is a list, each element in it
# is a tuple in the form of
# [Region of this sec_type, Fold start mark's Region, Fold End mark's region]
# the first one is the area really needed to fold
# latter ones are used to judge whether the current cursor's position
# is in fold start mark or end mark
def find_sec_regions(view, sec_type, execute_toc=False):

    extreme_fold = get_setting('extreme_fold') or None

    # if extreme_fold is "ALL" or we are called from one of the
    # Table of Contents commands and extreme_fold is set to "TOC" or is
    # unset
    if (
            extreme_fold == "ALL" or
            (
                execute_toc and
                (extreme_fold == "TOC" or extreme_fold is None)
            )
    ):
        extreme_fold = True
    else:
        extreme_fold = False

    begin_mark = get_begin_mark_pattern(sec_type)
    end_mark = get_end_mark_pattern(sec_type)

    # Find sec_type's parent mark in region range a to b
    # if find, return first match's index, else return None
    def find_parent_tags(sec_type, a, b):
        result = []
        s = view.substr(getRegion(a, b))
        for i in SECTION_TYPES[:SECTION_TYPES.index(sec_type)]:
            rs = re.findall(get_begin_mark_pattern(i), s)
            if len(rs) != 0:
                for r in rs:
                    m_pos = s.find(r)
                    m_size = len(r)
                    result.append(getRegion(a + m_pos, a + m_pos + m_size))

        # sorted by apperance
        return sorted(result, key=lambda x: x.begin())

    # Find sec_type's parent mark in region range a to b
    # if find, return first match's index, else return None
    def find_child_tags(sec_type, a, b):
        result = []
        s = view.substr(getRegion(a, b))
        for i in SECTION_TYPES[SECTION_TYPES.index(sec_type) + 1:]:
            rs = re.findall(get_begin_mark_pattern(i), s)
            if len(rs) != 0:
                for r in rs:
                    m_pos = s.find(r)
                    m_size = len(r)
                    result.append(getRegion(a + m_pos, a + m_pos + m_size))

        return sorted(result, key=lambda x: x.begin())

    start_regions = view.find_all(begin_mark)
    code_segs = []

    for i in range(len(start_regions)):
        current_mark = start_regions[i]
        if i + 1 < len(start_regions):
            next_mark = start_regions[i + 1]
        else:  # if there is no next marks
            end_doc = view.find(r'\\end{document}', 0)  # find \end{document}

            # ST2 compatible
            if not _ST3 and end_doc is None:
                end_doc = sublime.Region(-1, -1)

            if end_doc.begin() != -1:
                next_mark = end_doc
            else:
                next_mark = view.line(view.size())  # last line

        parent_tags = find_parent_tags(
            sec_type,
            current_mark.end(),
            next_mark.begin()
        )

        # if there is no parent tags
        if len(parent_tags) != 0:
            next_mark = parent_tags[0]

        child_tags = find_child_tags(
            sec_type,
            current_mark.end(),
            next_mark.begin()
        )

        # if extreme_fold set to all, search the end mark in the form of
        # '% ... (end)'
        if not extreme_fold:
            if len(child_tags) != 0:
                first_end_mark = view.find(end_mark, child_tags[-1].end())
            else:
                first_end_mark = view.find(end_mark, current_mark.end())

            if not _ST3 and first_end_mark is None:
                first_end_mark = sublime.Region(-1, -1)

            # if there is no end mark or next end mark is bellow next same
            # level's mark or a parents' mark
            if (
                first_end_mark.begin() == -1 or
                first_end_mark.begin() > next_mark.begin()
            ):
                current_end_mark = next_mark
            else:
                current_end_mark = first_end_mark
        else:
            current_end_mark = next_mark

        # if just one line at the last
        if current_mark.end() == current_end_mark.end():
            content = getRegion(current_mark.end(), current_mark.end())
        else:
            content = getRegion(
                current_mark.end(),
                view.line(current_end_mark.begin()).begin() - 1
            )
        code_segs.append([content, current_mark, current_end_mark])

    return code_segs


# Functions to find all foldable code segments
# This function is only used for fold to toc when
# extreme_fold set to None
def find_all_fold(view, depth=None, execute_toc=False):

    # Find fold depth
    if depth is not None:
        top_level = find_top_level(view)
        if top_level is not None:
            top_level = SECTION_TYPES.index(top_level)
            if top_level + depth - 1 > len(SECTION_TYPES):
                search_secs = SECTION_TYPES[top_level:]
            else:
                search_secs = SECTION_TYPES[top_level:top_level + depth]
    else:
        search_secs = SECTION_TYPES

    # Finding all regions need to be folded
    result = []
    for sec in search_secs:
        r = find_sec_regions(view, sec, execute_toc=execute_toc)
        if len(r) == 0:
            continue
        result += r

    return result


# Reform the whole buffer to foldable regions following
# the struct of TOC. Return result format is identical to
# find_sec_regions function, this function is only used for
# none extreme_fold satuations
def get_toc(view):
    fold_toc_depth = get_setting('fold_toc_depth') or None

    if fold_toc_depth is None:
        fold_toc_depth = 4

    # Get all codes
    code_segs = find_all_fold(view, depth=fold_toc_depth, execute_toc=True)

    # Process \documentclass, \begin{document} and \end{document} tags
    documentclass = view.find(r'\\documentclass(?:\[.*\])?\{.*\}', 0)
    if not _ST3 and documentclass is None:
        documentclass = sublime.Region(-1, -1)

    # if \documentclass tag exist!
    if documentclass.begin() > -1:
        doc_begin = view.find(r'\\begin\{document\}', 0)
        end_begin = view.find(r'\\end\{document\}', 0)

        # region contain preamble
        preamble_region = [
            sublime.Region(
                documentclass.end(),
                doc_begin.begin() - 1
            ),  # real preamble_region
            documentclass,
            view.line(doc_begin.begin() - 1)
        ]

        first_sec_mark = min(code_segs, key=lambda x: x[0].begin())
        doc_begin_region = [
            sublime.Region(
                doc_begin.end(),
                first_sec_mark[1].begin() - 1
            ),
            doc_begin,
            view.line(first_sec_mark[1].begin() - 1)
        ]

        doc_end_region = [
            sublime.Region(
                end_begin.end(),
                view.size()
            ),
            end_begin,
            view.line(view.size())
        ]

        code_segs.append(preamble_region)
        code_segs.append(doc_begin_region)
        code_segs.append(doc_end_region)

    # Sorted by start mark position
    code_segs = sorted(code_segs, key=lambda x: x[0].begin())

    # Generating toc fold region
    toc_strc = []
    for i in code_segs:
        if code_segs.index(i) < len(code_segs) - 1:
            j = code_segs[code_segs.index(i) + 1]
            if i[0].end() > j[0].begin():
                    toc_strc.append([
                        getRegion(
                            i[0].begin(),
                            view.line(j[0].begin()).begin() - 1
                        ),
                        i[1],  # i's start mark as new start mark
                        j[1]   # j's start mark as new end mark
                    ])
            else:
                toc_strc.append(i)
        else:
            toc_strc.append(i)

    return toc_strc


# Fold whole buffer to "Table of Contents",
# TOC depth is set by "fold_toc_depth" in settings files
class LatexFoldTocCommand(sublime_plugin.TextCommand):

    def run(self, edit, focus_current=False):
        view = self.view

        toc_strc = get_toc(view)

        point = view.sel()[0].end()
        for i in toc_strc:

            region_span = i[0].cover(i[1])

            # whether end mark is in the form of '% ... (end) form'
            # if it is, end mark should be in the region
            if re.search(r'%\s*.*\(end\)', view.substr(i[2])) is not None:
                region_span = region_span.cover(i[2])

            if focus_current and region_span.contains(point):
                continue
            else:
                view.fold(i[0])


# Command to fold expect levels.
class LatexFoldLevelCommand(sublime_plugin.TextCommand):

    def run(self, edit, fold_level=1):
        view = self.view

        # Get top level mark
        top_level = find_top_level(view)

        # Only work when there exist top level marks
        if top_level is not None:
            top_level = SECTION_TYPES.index(top_level)
            fold_level = top_level + (fold_level - 1)

            # make sure FoldLevel do not exceed the scope of secion_types
            if fold_level >= len(SECTION_TYPES):
                fold_level = len(SECTION_TYPES) - 1

            sec_type = SECTION_TYPES[fold_level]

            fold_regions = find_sec_regions(view, sec_type)
            for i in fold_regions:
                view.fold(i[0])


# Fold current section
class LatexFoldCurrentCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        extreme_fold = get_setting('extreme_fold') or None

        view = self.view
        point = view.sel()[0].end()

        fold_complete = False
        for sec in SECTION_TYPES[::-1]:  # Searching from the direct parent.
            regions = find_sec_regions(view, sec)
            for i in regions:

                region_span = i[0].cover(i[1])

                # if end mark is a norm end mark
                if extreme_fold != 'ALL':
                    if (
                        re.search(r'%\s*.*\(end\)', view.substr(i[2]))
                        is not None
                    ):
                        region_span = region_span.cover(i[2])

                if region_span.contains(point):
                    # if current foldable segment contains current point
                    # and have not been folded then fold it, or go to parent
                    # segment
                    if view.fold(i[0]):
                        fold_complete = True
                        return
                    else:
                        break

        if not fold_complete:
            documentclass = view.find(r'\\documentclass(?:\[.*\])?\{.*\}', 0)
            if not _ST3 and documentclass is None:
                documentclass = sublime.Region(-1, -1)

            # if \documentclass tag exist!
            if documentclass.begin() > -1:
                doc_begin = view.find(r'\\begin\{document\}', 0)
                end_begin = view.find(r'\\end\{document\}', 0)

                # region contain preamble
                preamble_region = sublime.Region(
                    documentclass.end(),
                    doc_begin.begin() - 1
                )

                first_sec_mark = min(
                    find_all_fold(view, depth=1),
                    key=lambda x: x[0].begin()
                )

                doc_begin_region = sublime.Region(
                    doc_begin.end(),
                    first_sec_mark[1].begin() - 1
                )

                doc_region = sublime.Region(
                    doc_begin.end(),
                    end_begin.begin() - 1
                )

                if preamble_region.contains(point):
                    view.fold(preamble_region)
                elif doc_begin_region.contains(point):
                    if not view.fold(doc_begin_region):
                        view.fold(doc_region)
                else:
                    view.fold(doc_region)


# Unfold current section.
class LatexUnfoldCurrentCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        extreme_fold = get_setting('extreme_fold')

        view = self.view
        point = view.sel()[0].end()

        documentclass = view.find(r'\\documentclass(?:\[.*\])?\{.*\}', 0)
        if not _ST3 and documentclass is None:
            documentclass = sublime.Region(-1, -1)

        # if \documentclass tag exist!
        if documentclass.begin() > -1:
            doc_begin = view.find(r'\\begin\{document\}', 0)
            end_begin = view.find(r'\\end\{document\}', 0)

            # region contain preamble
            preamble_region = sublime.Region(
                    documentclass.end(),
                    doc_begin.begin() - 1
                )

            first_sec_mark = min(
                find_all_fold(view, depth=1),
                key=lambda x: x[0].begin()
            )

            doc_begin_region = sublime.Region(
                doc_begin.end(),
                first_sec_mark[1].begin() - 1
            )

            # doc_region = sublime.Region(doc_begin.end(), end_begin.begin() - 1)

            if preamble_region.cover(documentclass).contains(point):
                unfold = view.unfold(preamble_region)
                if len(unfold) > 0:
                    view.sel().clear()
                    view.sel().add(preamble_region)
                    return

            if doc_begin_region.cover(doc_begin).contains(point):
                unfold = view.unfold(doc_begin_region)
                if len(unfold) > 0:
                    view.sel().clear()
                    view.sel().add(doc_begin_region)
                    return

        for sec in SECTION_TYPES[::-1]:  # Searching from the direct parent.
            regions = find_sec_regions(view, sec)
            for i in regions:

                region_span = i[0].cover(i[1])

                # print(i[2])

                # if end mark is a norm end mark
                if extreme_fold != 'ALL':
                    if re.search(r'%\s*.*\(end\)', view.substr(i[2])) is not None:
                        region_span = region_span.cover(i[2])

                if region_span.contains(point):
                    regions = view.unfold(i[0])
                    if len(regions) > 0:
                        view.sel().clear()
                        view.sel().add(i[0])
                        return
