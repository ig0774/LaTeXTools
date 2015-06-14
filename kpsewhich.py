from __future__ import print_function

import sublime

if sublime.version() < '3000':
    from latextools_utils.external_command import external_command
else:
    from .latextools_utils.external_command import external_command

__all__ = ['kpsewhich']

def kpsewhich(filename, file_format=None):
    # build command
    command = ['kpsewhich']
    if file_format is not None:
        command.append('-format=%s' % (file_format))
    command.append(filename)

    try:
        return_code, path, _ = external_command(command)
        if return_code == 0:
            return path
        else:
            sublime.error_message('An error occurred while trying to run kpsewhich. TEXMF tree could not be accessed.')
    except OSError:
        sublime.error_message('Could not run kpsewhich. Please ensure that your texpath setting is configured correctly in the LaTeXTools settings.')

    return None
