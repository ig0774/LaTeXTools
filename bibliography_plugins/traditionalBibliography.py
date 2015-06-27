from latextools_plugin import LaTeXToolsPlugin

from kpsewhich import kpsewhich

import codecs
import os
import re

KP = re.compile(r'@[^\{]+\{(.+),')
# new and improved regex
# we must have "title" then "=", possibly with spaces
# then either {, maybe repeated twice, or "
# then spaces and finally the title
# # We capture till the end of the line as maybe entry is broken over several lines
# # and in the end we MAY but need not have }'s and "s
# tp = re.compile(r'\btitle\s*=\s*(?:\{+|")\s*(.+)', re.IGNORECASE)  # note no comma!
# # Tentatively do the same for author
# # Note: match ending } or " (surely safe for author names!)
# ap = re.compile(r'\bauthor\s*=\s*(?:\{|")\s*(.+)(?:\}|"),?', re.IGNORECASE)
# # Editors
# ep = re.compile(r'\beditor\s*=\s*(?:\{|")\s*(.+)(?:\}|"),?', re.IGNORECASE)
# # kp2 = re.compile(r'([^\t]+)\t*')
# # and year...
# # Note: year can be provided without quotes or braces (yes, I know...)
# yp = re.compile(r'\byear\s*=\s*(?:\{+|"|\b)\s*(\d+)[\}"]?,?', re.IGNORECASE)

# This may speed things up
# So far this captures: the tag, and the THREE possible groups
MULTIP = re.compile(r'\b(author|title|year|editor|journal|eprint)\s*=\s*(?:\{|"|\b)(.+?)(?:\}+|"|\b)\s*,?\s*\Z',re.IGNORECASE)

class TraditionalBibliographyPlugin(LaTeXToolsPlugin):
    def find_bibliography_files(self, root_file):
        bib_files = []

        rootdir = os.path.dirname(root_file)

        # recursively search all linked tex files to find all
        # included bibliography tags in the document and extract
        # the absolute filepaths of the bib files
        def _find_bib_files(src):
            if src[-4:].lower() != ".tex":
                src = src + ".tex"

            file_path = os.path.normpath(os.path.join(rootdir, src))
            print("Searching file: " + repr(file_path))

            # read src file and extract all bibliography tags
            try:
                src_file = codecs.open(file_path, "r", 'UTF-8')
            except IOError:
                print ("LaTeXTools WARNING: cannot open included file " + file_path)
                return

            src_content = re.sub("%.*", "", src_file.read())
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

            bibtags =  re.findall(r'\\bibliography\{[^\}]+\}', src_content)
            bibtags += re.findall(r'\\addbibresource\{[^\}]+.bib\}', src_content)

            # extract absolute filepath for each bib file
            for tag in bibtags:
                bfiles = re.search(r'\{([^\}]+)', tag).group(1).split(',')
                for bf in bfiles:
                    if bf[-4:].lower() != '.bib':
                        bf = bf + '.bib'
                    # We join with rootdir, the dir of the master file
                    candidate_file = os.path.normpath(os.path.join(rootdir, bf))
                    # if the file doesn't exist, search the default tex paths
                    if not os.path.exists(candidate_file):
                        candidate_file = kpsewhich(bf, 'mlbib')

                    if candidate_file is not None and os.path.exists(candidate_file):
                        bib_files.append(candidate_file)

            # search through input tex files recursively
            for f in re.findall(r'\\(?:input|include)\{[^\}]+\}', src_content):
                input_file = re.search(r'\{([^\}]+)', f).group(1)
                _find_bib_files(input_file)
        return bib_files

    def get_entries(self, *bib_files):
        entries = []
        for bibfname in bib_files:
            # # THIS IS NO LONGER NEEDED as find_bib_files() takes care of it
            # if bibfname[-4:] != ".bib":
            #     bibfname = bibfname + ".bib"
            # texfiledir = os.path.dirname(view.file_name())
            # # fix from Tobias Schmidt to allow for absolute paths
            # bibfname = os.path.normpath(os.path.join(texfiledir, bibfname))
            # print repr(bibfname)
            try:
                bibf = codecs.open(bibfname,'r','UTF-8', 'ignore')  # 'ignore' to be safe
            except IOError:
                print ("Cannot open bibliography file %s !" % (bibfname,))
                sublime.status_message("Cannot open bibliography file %s !" % (bibfname,))
                continue
            else:
                bib = bibf.readlines()
                bibf.close()
            print ("%s has %s lines" % (repr(bibfname), len(bib)))

            entry = {
                        "keyword": "",
                        "title": "",
                        "author": "",
                        "year": "",
                        "editor": "",
                        "journal": "",
                        "eprint": ""
                    }

            for line in bib:
                line = line.strip()
                # Let's get rid of irrelevant lines first
                if line == "" or line[0] == '%':
                    continue
                if line.lower()[0:8] == "@comment":
                    continue
                if line.lower()[0:7] == "@string":
                    continue
                if line.lower()[0:9] == "@preamble":
                    continue
                if line[0] == "@":
                    # First, see if we can add a record; the keyword must be non-empty, other fields not
                    if entry["keyword"]:
                        entries.append(dict(entry))

                        # Now reset for the next iteration
                        entry["keyword"] = ""
                        entry["title"] = ""
                        entry["year"] = ""
                        entry["author"] = ""
                        entry["editor"] = ""
                        entry["journal"] = ""
                        entry["eprint"] = ""
                    # Now see if we get a new keyword
                    kp_match = KP.search(line)
                    if kp_match:
                        entry["keyword"] = kp_match.group(1)  # No longer decode. Was: .decode('ascii','ignore')
                    else:
                        print ("Cannot process this @ line: " + line)
                        print ("Previous keyword (if any): " + entry["keyword"])
                    continue
                # Now test for title, author, etc.
                # Note: we capture only the first line, but that's OK for our purposes
                multip_match = MULTIP.search(line)
                if multip_match:
                    key = multip_match.group(1).lower()     # no longer decode. Was:    .decode('ascii','ignore')
                    value = multip_match.group(2)           #                           .decode('ascii','ignore')
                    entry[key] = value
                continue

            # at the end, we are left with one bib entry
            entries.append(entry)

            print("Found %d total bib entries" % (len(entries),))

            for entry in entries:
                # # Filter out }'s at the end. There should be no commas left
                entry['title'] = \
                    entry['title'].replace(
                        '{\\textquoteright}', '').replace('{','').replace('}','')

                entry['author_short'] = format_author(entry['author'])

        return entries

    def on_insert_citation(self, keyword):
        print('Inserted {0}'.format(keyword))
