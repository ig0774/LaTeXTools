from __future__ import print_function

import re
import os
import codecs
import shlex
import sys
import traceback

import sublime
import sublime_plugin

try:
    from getTeXRoot import get_tex_root
except ImportError:
    from .getTeXRoot import get_tex_root

try:
    from latextools_utils import get_tex_extensions, is_tex_buffer, get_setting
except ImportError:
    from .latextools_utils import get_tex_extensions, is_tex_buffer, get_setting

try:
    from latextools_utils.external_command import external_command
except ImportError:
    from .latextools_utils.external_command import external_command

if sys.version_info < (3, 0):
    strbase = basestring
    _ST3 = True
else:
    strbase = str


# TODO this might be moved to a generic util
def run_after_loading(view, func):
    """Run a function after the view has finished loading"""
    def run():
        if view.is_loading():
            sublime.set_timeout(run, 10)
        else:
            # add an additional delay, because it might not be ready
            # even if the loading function returns false
            sublime.set_timeout(func, 10)
    run()


class JumptoTexFileCommand(sublime_plugin.TextCommand):

    def run(self, edit, auto_create_missing_folders=True,
            auto_insert_root=True):
        view = self.view
        if not is_tex_buffer(view):
            return

        window = view.window()
        tex_root = get_tex_root(view)

        if tex_root is None:
            sublime.status_message("Save your current file first")
            return

        # the base path to the root file
        base_path, base_name = os.path.split(tex_root)

        reg = re.compile(
            r"\\(?:input|include|subfile)\{(?P<file>[^}]+)\}",
            re.UNICODE
        )

        img_reg = re.compile(
            r"\\includegraphics(\[.*\])?"
            r"\{(?P<file>[^\}]+)\}",
            re.UNICODE
        )

        for sel in view.sel():
            line = view.substr(view.line(sel))

            # is tex file?
            g = re.search(reg, line)
            if g and g.group("file"):
                new_file_name = g.group('file')

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

                # allow absolute paths on \include or \input
                isabs = os.path.isabs(containing_folder)
                if not isabs:
                    containing_folder = os.path.normpath(
                        os.path.join(base_path, containing_folder))

                # create the missing folder
                if auto_create_missing_folders and\
                        not os.path.exists(containing_folder):
                    try:
                        os.makedirs(containing_folder)
                    except OSError:
                        # most likely a permissions error
                        print(u'Error occurred while creating path "{0}"'
                              .format(containing_folder))
                        traceback.print_last()
                    else:
                        print(u'Created folder: "{0}"'
                              .format(containing_folder))

                if not os.path.exists(containing_folder):
                    sublime.status_message(
                        "Cannot open tex file as folders are missing")
                    continue

                is_root_inserted = False
                full_new_path = os.path.join(containing_folder, new_file_name)
                if auto_insert_root and not os.path.exists(full_new_path):
                    if isabs:
                        root_path = tex_root
                    else:
                        root_path = os.path.join(
                            os.path.relpath(base_path, containing_folder),
                            base_name)

                    # Use slashes consistent with TeX's usage
                    if sublime.platform() == 'windows':
                        root_path = root_path.replace(u'\\', u'/')

                    root_string = u'%!TEX root = {0}\n'.format(root_path)
                    try:
                        with codecs.open(full_new_path, "w", "utf8") as new_file:
                            new_file.write(root_string)
                        is_root_inserted = True
                    except OSError:
                        print(u'An error occurred while creating file "{0}"'\
                                .format(new_file_name))
                        traceback.print_last()

                # open the file
                new_view = window.open_file(full_new_path)

                # await opening and move cursor to end of the new view
                # (does not work on st2)
                if _ST3 and auto_insert_root and is_root_inserted:
                    def set_caret_position():
                        cursor_pos = len(root_string)
                        new_view.sel().clear()
                        new_view.sel().add(sublime.Region(cursor_pos,
                                                          cursor_pos))
                    run_after_loading(new_view, set_caret_position)

            # is image?
            g = re.search(img_reg, line)
            if g:
                file_name = g.group("file")

                file_path = os.path.normpath(
                    os.path.join(base_path, file_name))
                _, extension = os.path.splitext(file_path)

                extension = extension[1:]  # strip the leading point
                if not extension:
                    # TODO might get this extensions from somewhere else
                    for ext in get_setting('image_extensions',
                            ["eps", "png", "pdf", "jpg", "jpeg"]):
                        test_path = file_path + "." + ext

                        if os.path.exists(test_path):
                            extension = ext
                            file_path = test_path
                            break

                if not os.path.exists(file_path):
                    sublime.status_message(
                       "file does not exists: " + file_path)
                    continue

                def run_command(command):
                    if isinstance(command, strbase):
                        command = shlex.split(command)

                    command.append(file_path)
                    external_command(command)

                settings = get_setting("open_image_command", {})
                commands = settings.get(sublime.platform(), None)

                if commands is None:
                    self.view.window().open_file(file_path)
                elif isinstance(commands, strbase):
                    run_command(commands)
                else:
                    for d in commands:
                        # validate the entry
                        if "command" not in d:
                            message = "Invalid entry {0}, missing: 'command'"\
                                .format(str(d))
                            sublime.status_message(message)
                            print(message)
                            continue
                        # check whether the extension matches
                        if "extension" in d:
                            if extension == d["extension"] or\
                                    extension in d["extension"]:
                                run_command(d["command"])
                                break
                        # if no extension matches always run the command
                        else:
                            run_command(d["command"])
                            break
                    else:
                        sublime.status_message(
                            "No opening command for {0} defined"
                            .format(extension))
                        view.window().open_file(file_path)
