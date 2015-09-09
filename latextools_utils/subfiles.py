from __future__ import print_function

import codecs
import os
import re

try:
    from ..latextools_utils import is_tex_file, get_tex_extensions
except:
    from latextools_utils import is_tex_file, get_tex_extensions

# I've combined this into one regex in case import order becomes important
INPUT_FILE = re.compile(r'''
    \\(?:input|include|subfile)\{([^\}]+)\}|
    \\(?:(?:sub)?import)[*]?\{([^\}]+)\}\{([^\}]+)\}
''', re.MULTILINE)
DOCUMENT_START = re.compile(r'\\begin\{document\}')

# recursively search all linked tex files to find all
# included bibliography tags in the document and extract
# the absolute filepaths of the bib files
def walk_subfiles(rootdir, src, preamble_only=False):
    # rootdir has to be passed along because \input and \include
    # are relative to the root file
    if not is_tex_file(src):
        src_tex_file = None
        for ext in get_tex_extensions():
            src_tex_file = ''.join((src, ext))
            if os.path.exists(os.path.join(rootdir, src_tex_file)):
                src = src_tex_file
        if src != src_tex_file:
            print("Could not find file {0}".format(src))
            return

    file_path = os.path.normpath(os.path.join(rootdir, src))
    print("Scanning file: " + repr(file_path))

    # We open with utf-8 by default. If you use a different encoding, too bad.
    # If we really wanted to be safe, we would read until \begin{document},
    # then stop. Hopefully we wouldn't encounter any non-ASCII chars there.
    # But for now do the dumb thing.
    try:
        src_file = codecs.open(file_path, "r", 'UTF-8')
    except IOError:
        print ("LaTeXTools WARNING: cannot open included file " + file_path)
        return

    src_content = re.sub('%.*', '', src_file.read())
    src_file.close()

    m = re.search(r"\\usepackage\[(.*?)\]\{inputenc\}", src_content)
    if m:
        f = None
        try:
            f = codecs.open(file_path, "r", m.group(1))
            src_content = re.sub("%.*", "", f.read())
        except:
            pass
        finally:
            if f and not f.closed:
                f.close()

    yield src_content

    document_start = None
    # search through input tex files recursively
    if preamble_only:
        src_content, document_start = re.split(DOCUMENT_START, src_content, 1)

    for match in re.findall(INPUT_FILE, src_content):
        # input / include / subfile
        if match[0]:
            for src_content in walk_subfiles(rootdir, match[0], preamble_only):
                yield src_content
        # import / subimport
        elif match[1]:
            if not match[2]:
                continue

            if os.path.isabs(match[1]):
                new_root = match[1]
            else:
                new_root = os.path.normpath(
                    os.path.join(rootdir, match[1]))

            for src_content in walk_subfiles(new_root, match[2], preamble_only):
                yield src_content

    if document_start is not None:
        raise StopIteration()
