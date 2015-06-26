import sublime
import sublime_plugin

BIBLATEX_SYNTAX = 'Packages/LaTeXTools/BibLaTeX.tmLanguage'

# simple listener to default bib files to BibLaTeX syntax if the
# `use_biblatex` configuration option has been set in either the user's
# LaTeXTools.sublime-settings or the current project settings
class BibLaTeXSyntaxListener(sublime_plugin.EventListener):
    def on_load(self, view):
        self.detect_and_apply_syntax(view)

    def on_post_save(self, view):
        self.detect_and_apply_syntax(view)

    def detect_and_apply_syntax(self, view):
        if view.is_scratch() or not view.file_name():
            return

        current_syntax = view.settings().get('syntax')
        if current_syntax == BIBLATEX_SYNTAX:
            return

        global_settings = sublime.load_settings('LaTeXTools.sublime-settings')
        if not view.settings().get('use_biblatex',
            global_settings.get('use_biblatex', False)):
            return

        file_name = view.file_name()
        if file_name.endswith('bib'):
            view.set_syntax_file(BIBLATEX_SYNTAX)