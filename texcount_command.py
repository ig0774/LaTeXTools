from __future__ import print_function
import sublime
import sublime_plugin

import os

if sublime.version() < '3000':
    from getTeXRoot import get_tex_root
    from get_texpath import get_texpath
    from external_command import external_command
else:
    from .getTeXRoot import get_tex_root
    from .get_texpath import get_texpath
    from .external_command import external_command

class TexcountCommand(sublime_plugin.TextCommand):
    """
    Simple TextCommand to run TeXCount against the current document
    """

    def run(self, edit, **args):
        tex_root = get_tex_root(self.view)

        if not os.path.exists(tex_root):
            sublime.error_message(
                'Tried to run TeXCount on non-existent file. Please ensure all files are saved before invoking TeXCount.'
            )
            return

        command = ['texcount', '-total', '-merge', '-utf8']
        cwd = os.path.dirname(tex_root)
        command.append(os.path.basename(tex_root))

        try:
            return_code, result, stderr = external_command(
                command, cwd=cwd
            )
            if return_code == 0:
                self.view.window().show_quick_panel(result.splitlines()[1:-4], None)
            else:
                sublime.error_message(
                    'Error while running TeXCount: {}'.format(
                        str(stderr)
                    )
                )
        except OSError:
            sublime.error_message(
                'Could not run texcount. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.'
            )
