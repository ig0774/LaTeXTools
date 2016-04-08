# ST2/ST3 compat
import sublime
if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
    _ST3 = False
    strbase = basestring

    # reraise implementation from 6
    exec("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")
else:
    _ST3 = True
    strbase = str

    # reraise implementation from 6
    def reraise(tp, value, tb=None):
        if value is None:
            value = tp()
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

import os
import re
import subprocess
import sys
# This will work because makePDF.py puts the appropriate
# builders directory in sys.path
from pdfBuilder import PdfBuilder

# Standard LaTeX warning
CITATIONS_REGEX = re.compile(r"Warning: Citation `.+' on page \d+ undefined")
# BibLaTeX outputs a different message from BibTeX, so we must catch that too
BIBLATEX_REGEX = re.compile(r"Package biblatex Warning: Please \(re\)run (\S*)")
# Used to indicate a subdirectory that needs to be made for a file input using
# \include
FILE_WRITE_ERROR_REGEX = re.compile(r"! I can't write on file `(.*)/([^/']*)'")


#----------------------------------------------------------------
# BasicBuilder class
#
# This is a more fully functional verion of the Simple Builder
# concept. It implements the same building features as the
# Traditional builder.
#
class BasicBuilder(PdfBuilder):

    def __init__(self, *args):
        super(BasicBuilder, self).__init__(*args)
        self.name = "Basic Builder"
        self.bibtex = self.builder_settings.get('bibtex', 'bibtex')
        self.display_log = self.builder_settings.get("display_log", False)

    def commands(self):
        # Print greeting
        self.display("\n\nBasic Builder: ")

        engine = self.engine
        if "la" not in engine:
            # we need the command rather than the engine
            engine = {
                "pdftex": u"pdflatex",
                "xetex": u"xelatex",
                "luatex": u"lualatex"
            }.get(engine, u'pdflatex')

        latex = [engine, u"-interaction=nonstopmode", u"-synctex=1"]
        biber = [u"biber"]

        if self.aux_directory is not None:
            self.make_directory(self.aux_directory)

            if self.aux_directory == self.output_directory:
                latex.append(u'--output-directory=' + self.aux_directory)
            else:
                latex.append(u'--aux-directory=' + self.aux_directory)

            biber.append(u'--output-directory=' + self.aux_directory)

        if (
            self.output_directory is not None and
            self.output_directory != self.aux_directory
        ):
            self.make_directory(self.aux_directory)
            latex.append(u'--output-directory=' + self.output_directory)

        for option in self.options:
            latex.append(option)

        latex.append(self.base_name)

        yield (latex, "running {0}...".format(engine))
        self.display("done.\n")
        self.log_output()

        # Check if any subfolders need to be created
        # this adds a number of potential runs as LaTeX treats being unable
        # to open output files as fatal errors
        if self.aux_directory is not None:
            while True:
                start = 0
                added_directory = False
                while True:
                    match = FILE_WRITE_ERROR_REGEX.search(self.out, start)
                    if match:
                        self.make_directory(
                            os.path.join(
                                self.aux_directory,
                                match.group(1)
                            )
                        )
                        start = match.end(1)
                        added_directory = True
                    else:
                        break
                if added_directory:
                    yield (latex, "running {0}... ".format(engine))
                    self.display("done.\n")
                    self.log_output()
                else:
                    break

        # Check for citations
        # Use search, not match: match looks at the beginning of the string
        # We need to run pdflatex twice after bibtex
        if (
            CITATIONS_REGEX.search(self.out) or
            "Package natbib Warning: There were undefined citations."
                in self.out
        ):
            yield (self.run_bibtex(), "running bibtex...")
            self.display("done.\n")
            self.log_output()

            for i in range(2):
                yield (latex, "running {0}...".format(engine))
                self.display("done.\n")
                self.log_output()
        else:
            match = BIBLATEX_REGEX.search(self.out)
            if match:
                if match.group(1).lower() == 'biber':
                    yield (biber + [self.base_name], "running biber...")
                else:
                    yield (
                        self.run_bibtex(match.group(1).lower()),
                        "running {0}...".format(match.group(1).lower9)
                    )
                self.display("done.\n")
                self.log_output()

                for i in range(2):
                    yield (latex, "running {0}...".format(engine))
                    self.display("done.\n")
                    self.log_output()

        # Check for changed labels
        # Do this at the end, so if there are also citations to resolve,
        # we may save one pdflatex run
        if "Rerun to get cross-references right." in self.out:
            yield (latex, "running {0}...".format(engine))
            self.display("done.\n")
            self.log_output()
            self.display("done.\n")

    def log_output(self):
        if self.display_log:
            self.display("\nCommand results:\n")
            self.display(self.out)
            self.display("\n\n")

    def make_directory(self, directory):
        if not os.path.exists(directory):
            try:
                print('making directory ' + directory)
                os.makedirs(directory)
            except OSError:
                if not os.path.exists(directory):
                    reraise(*sys.exc_info())

    def run_bibtex(self, command=None):
        if command is None:
            command = [self.bibtex]
        elif isinstance(command, strbase):
            command = [command]

        # to get bibtex to work with the output directory, we change the
        # cwd to the output directory and add the main directory to
        # BIBINPUTS and BSTINPUTS
        env = dict(os.environ)
        cwd = self.tex_dir

        if self.aux_directory is not None:
            # cwd is, at the point, the path to the main tex file
            if _ST3:
                env['BIBINPUTS'] = cwd + os.pathsep + env.get('BIBINPUTS', '')
                env['BSTINPUTS'] = cwd + os.pathsep + env.get('BSTINPUTS', '')
            else:
                env['BIBINPUTS'] = \
                    (cwd + os.pathsep + env.get('BIBINPUTS', '')).encode(
                        sys.getfilesystemencoding()
                    )
                env['BSTINPUTS'] = \
                    (cwd + os.pathsep + env.get('BSTINPUTS', '')).encode(
                        sys.getfilesystemencoding()
                    )
            # now we modify cwd to be the output directory
            # NOTE this cwd is not reused by any of the other command
            cwd = self.aux_directory

        startupinfo = None
        preexec_fn = None

        if sublime.platform() == 'windows':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        else:
            preexec_fn = os.setsid

        command.append(self.base_name)
        print(command)
        bib_proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            shell=False,
            env=env,
            cwd=cwd,
            preexec_fn=preexec_fn
        )

        return bib_proc
