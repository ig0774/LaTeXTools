from __future__ import print_function

import re
import os
import traceback

import sublime
import sublime_plugin

try:
    from .getTeXRoot import get_tex_root
except ImportError:
    from getTeXRoot import get_tex_root

try:
    from .latextools_utils import get_tex_extensions, is_tex_buffer
except ImportError:
    from latextools_utils import get_tex_extensions, is_tex_buffer

try:
    from .latextools_utils.subfiles import INPUT_FILE
except ImportError:
    from latextools_utils.subfiles import INPUT_FILE


class JumptoTexFileCommand(sublime_plugin.TextCommand):

    def run(self, edit, auto_create_missing_folders=True,
            auto_insert_root=True):
        view = self.view
        if not is_tex_buffer(view):
            return

        tex_root = get_tex_root(view)

        if tex_root is None:
            sublime.status_message("Save your current file first")
            return

        # the base path to the root file
        base_path, base_name = os.path.split(tex_root)

        for sel in view.sel():
            line = view.substr(view.line(sel))
            g = re.search(INPUT_FILE, line)
            if g and (g.group("file") or g.group("file2")):
                new_file_name = g.group('file') or g.group("file2")

                _, ext = os.path.splitext(new_file_name)
                if ext == '':
                    new_file_name += '.tex'
                elif ext.lower() not in get_tex_extensions():
                    sublime.status_message(
                        "Cannot open file '{0}' as it has an unrecognized extension".format(
                            new_file_name))
                    continue

                # clean-up any directory manipulating components
                new_file_name = os.path.normpath(new_file_name)

                containing_folder, new_file_name = os.path.split(new_file_name)

                original_containing_folder = containing_folder

                # allow absolute paths on \include or \input
                if not os.path.isabs(containing_folder):
                    containing_folder = os.path.normpath(
                        os.path.join(base_path, containing_folder))
                elif containing_folder == '':
                    containing_folder = base_path

                # create the missing folder / check if all path folders exists
                if not os.path.exists(containing_folder):
                    if auto_create_missing_folders:
                        try:
                            os.makedirs(containing_folder, exist_ok=True)
                        except OSError:
                            # most likely a permissions error
                            print('Error occurred while creating path "{0}"'.format(
                                    containing_folder))
                            traceback.print_last()
                        else:
                            print('Created folder: "{0}"'.format(containing_folder))

                if not os.path.exists(containing_folder):
                    sublime.status_message(
                        "Cannot open tex file as folders are missing")
                    continue

                full_new_path = os.path.join(containing_folder, new_file_name)
                if auto_insert_root:
                    if not os.path.exists(full_new_path):
                        # hackish way to attempt to determine if the root is
                        # referenced from this file as an absolute or relative
                        # path
                        current_file_folder = os.path.split(view.file_name())[0]
                        if base_path != current_file_folder:
                            root_path = os.path.join(base_path, base_name)
                        elif os.path.isabs(original_containing_folder):
                            root_path = os.path.abspath(
                                os.path.join(base_path, base_name))
                        else:
                            root_path = os.path.join(
                                os.path.relpath(base_path, containing_folder),
                                base_name)

                        # Use slashes consistent with TeX's usage
                        if sublime.platform() == 'windows':
                            root_path = root_path.replace('\\', '/')

                        root_string = '%!TEX root = {0}\n'.format(root_path)
                        try:
                            with open(full_new_path, 'a', encoding='utf-8') as new_file:
                                new_file.write(root_string)
                        except OSError:
                            print('An error occurred while creating file "{0}"'.format(
                                new_file_name))
                            traceback.print_last()

                new_view = self.view.window().open_file(full_new_path)

                # move cursor to end of the new view
                if auto_insert_root:
                    new_view.sel().clear()
                    cursor_pos = len(root_string)
                    new_view.sel().add(sublime.Region(cursor_pos, cursor_pos))
