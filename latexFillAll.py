from __future__ import print_function

import sublime
import sublime_plugin
import re

if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    from latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from latex_input_completions import TEX_INPUT_FILE_REGEX
    from getRegion import get_Region
else:
    _ST3 = True
    from .latex_cite_completions import OLD_STYLE_CITE_REGEX, NEW_STYLE_CITE_REGEX, match
    from .latex_ref_completions import OLD_STYLE_REF_REGEX, NEW_STYLE_REF_REGEX
    from .latex_input_completions import TEX_INPUT_FILE_REGEX
    from .getRegion import get_Region

# used to flag whether command is triggered for cite
TRIGGER_CITE = False

def get_current_word(view, point):
    line_prefix = view.substr(get_Region(view.line(point).a, point))[::-1]
    line_suffix = view.substr(get_Region(point, view.line(point).b))

    # prefix is the characters before caret
    prefix = re.match(r'([^{}]*)\{', line_prefix).group(1)
    suffix = re.match(r'([^{}]*)\}', line_suffix).group(1)

    return prefix[::-1], suffix

class LatexFillAllCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        point = view.sel()[0].b

        # Current lines, used to detemine whether is input, include, cite, or includegraphics
        line = view.substr(get_Region(view.line(point).a, point))[::-1]

        # if \cite or \ref
        if (OLD_STYLE_CITE_REGEX.match(line) or
            NEW_STYLE_CITE_REGEX.match(line) or
            OLD_STYLE_REF_REGEX.match(line)  or
            NEW_STYLE_REF_REGEX.match(line)):
                prefix, suffix = get_current_word(view, point)
                current_word = prefix + suffix
                if current_word != '':
                    start_point = point - len(prefix)
                    end_point   = point - len(suffix)
                    view.run_command(
                        'latex_tools_replace',
                        {
                            'a': start_point,
                            'b': end_point,
                            'replacement': ''
                        })
                view.run_command('latex_ref_cite')

        # if \input, \include or \includegraphics
        if TEX_INPUT_FILE_REGEX.match(line):
            prefix, suffix = get_current_word(view, point)
            current_word = prefix + suffix
            if current_word != '':
                current_word = prefix + suffix
                if current_word != '':
                    start_point = point - len(prefix)
                    end_point   = point - len(suffix)
                    view.run_command(
                        'latex_tools_replace',
                        {
                            'a': start_point,
                            'b': end_point,
                            'replacement': ''
                        })
            view.run_command("latex_fill_input")

class OnLatexFillAllReplacement(sublime_plugin.EventListener):
    # This trigger is used to delete the last "}"
    # character inserted by latex_cite command 
    # when modifing the keyword between two commas.
    def on_selection_modified(self, view):
        global TRIGGER_CITE

        # If selection is modifed by fill all commands
        if TRIGGER_CITE:
            caret = view.sel()[0].b
            last_char = view.substr(get_Region(caret-1, caret))
            if last_char == '}':
                TRIGGER_CITE = False # Turn off triggers
                view.run_command('latex_tools_replace', {'a': caret-1, 'b': caret, 'replacement': ''})
