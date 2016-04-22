from __future__ import print_function
import sublime
import sublime_plugin

import os
from subprocess import CalledProcessError

if sublime.version() < '3000':
    from latextools_utils.external_command import check_output
    from getTeXRoot import get_tex_root
else:
    from .latextools_utils.external_command import check_output
    from .getTeXRoot import get_tex_root


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

        sub_level = args.get('sub_level', 'chapter')

        command = ['texcount', '-merge', '-sub=' + sub_level, '-utf8']
        cwd = os.path.dirname(tex_root)
        command.append(os.path.basename(tex_root))

        try:
            res_split = check_output(command, cwd=cwd).splitlines()
            self.view.window().show_quick_panel(
                res_split[1:4] + res_split[9:], None
            )
        except CalledProcessError as e:
            sublime.error_message(
                'Error while running TeXCount: {0}'.format(
                    str(e.output)
                )
            )
        except OSError:
            sublime.error_message(
                'Could not run texcount. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.'
            )
