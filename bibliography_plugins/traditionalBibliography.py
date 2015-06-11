from latextools_plugin import LaTeXToolsPlugin

import codecs
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
TITLE_SEP = re.compile(':|\.|\?')

# format author field
def format_author(authors):
    # print(authors)
    # split authors using ' and ' and get last name for 'last, first' format
    authors = [a.split(", ")[0].strip(' ') for a in authors.split(" and ")]
    # get last name for 'first last' format (preserve {...} text)
    authors = [a.split(" ")[-1] if a[-1] != '}' or a.find('{') == -1 else re.sub(r'{|}', '', a[len(a) - a[::-1].index('{'):-1]) for a in authors]
    #     authors = [a.split(" ")[-1] for a in authors]
    # truncate and add 'et al.'
    if len(authors) > 2:
        authors = authors[0] + " et al."
    else:
        authors = ' & '.join(authors)
    # return formated string
    # print(authors)
    return authors

class TraditionalBibliographyPlugin(LaTeXToolsPlugin):
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
                if not entry['author']:
                    entry['author'] = entry['editor'] or '????'
                if not entry['journal']:
                    entry['journal'] = entry['eprint'] or '????'

                # # Filter out }'s at the end. There should be no commas left
                entry['title'] = \
                    entry['title'].replace(
                        '{\\textquoteright}', '').replace('{','').replace('}','')

                entry['author_short'] = format_author(entry['author'])

                # short title
                title_short = TITLE_SEP.split(entry['title'])[0]
                if len(title_short) > 60:
                    title_short = title_short[:60] + '...'
                entry['title_short'] = title_short

        return entries

    def on_insert_citation(self, keyword):
        print('Inserted {}'.format(keyword))
