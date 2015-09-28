import re


def split_tex_string(string, maxsplit=-1, sep=None):
    '''
    A variation of string.split() to support tex strings

    In particular, ignores text in brackets, no matter how deeply nested and
    defaults to breaking on any space char or ~.
    '''

    if sep is None:
        # tilde == non-breaking space
        sep = r'(?u)[\s~]+'
    sep_re = re.compile(sep)

    result = []

    # track ignore separators in braces
    brace_level = 0
    # calculate once
    string_len = len(string)
    word_start = 0
    splits = 0

    for pos, c in enumerate(string):
        if c == '{':
            brace_level += 1
        elif c == '}':
            brace_level -= 1
        elif brace_level == 0 and pos > 0:
            matcher = sep_re.match(string[pos:])
            if matcher:
                sep_len = len(matcher.group())
                if pos + sep_len <= string_len:
                    result.append(string[word_start:pos])
                    word_start = pos + sep_len

                    splits += 1
                    if splits == maxsplit:
                        break

    if word_start < string_len:
        result.append(string[word_start:])

    return [part.strip() for part in result if part]


def tokenize_list(list_str):
    return split_tex_string(list_str, sep=r'(?iu)[\s~]+and(?:[\s~]+|$)')
