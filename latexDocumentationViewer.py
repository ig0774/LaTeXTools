from __future__ import print_function

import sublime
import sublime_plugin

if sublime.version() < '3000':
    strbase = basestring
    from latextools_utils.external_command import external_command
else:
    strbase = str
    from .latextools_utils.external_command import external_command

def is_latex_doc(view):
    point = view.sel()[0].b
    return (
        view.score_selector(point, "text.tex.latex") > 0 or
        view.score_selector(point, "text.bibtex") > 0
    )

class LatexPkgDocCommand(sublime_plugin.WindowCommand):
    def run(self):
        window = self.window
        def _on_done(file):
            if (
                file is not None and
                isinstance(file, strbase) and
                file != ''
            ):
                window.run_command('latex_view_doc',
                    {'file': file})

        window.show_input_panel(
            'View documentation for which package?',
            '',
            _on_done,
            None,
            None
        )

    def is_visible(self):
        return is_latex_doc(self.window.active_view())

    def is_enabled(self):
        return is_latex_doc(self.window.active_view())

class LatexViewDocCommand(sublime_plugin.WindowCommand):
    def run(self, file):
        if file is None:
            raise Exception('File must be specified')
        if not isinstance(file, strbase):
            raise TypeError('File must be a string')

        command = ['texdoc', file]

        try:
            return_code, _, _ = external_command(command)
            if return_code != 0:
                sublime.eror_message('An error occurred while trying to run texdoc.')
        except OSError:
            sublime.error_message('Could not run texdoc. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.')

    def is_visible(self):
        return False  # hide this from menu

    def is_enabled(self):
        return is_latex_doc(self.window.active_view())
