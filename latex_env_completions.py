import os

try:
    _ST3 = True
    from .latex_fill_all import FillAllHelper
    from .latextools_utils import get_setting
    from .latex_cwl_completions import (
        is_cwl_available, get_packages, get_cwl_completions,
        BEGIN_END_BEFORE_REGEX
    )
    from .getTexRoot import get_tex_root
except:
    _ST3 = False
    from latex_fill_all import FillAllHelper
    from latextools_utils import get_setting
    from latex_cwl_completions import (
        is_cwl_available, get_packages, get_cwl_completions,
        BEGIN_END_BEFORE_REGEX
    )
    from getTeXRoot import get_tex_root


class EnvFillAllHelper(FillAllHelper):

    def get_completions(self, view, prefix, line):
        if not is_cwl_available():
            return

        # get the current documents package list
        packages = get_setting('cwl_list', [
            "tex.cwl",
            "latex-209.cwl",
            "latex-document.cwl",
            "latex-l2tabu.cwl",
            "latex-mathsymbols.cwl"
        ])

        if get_setting('cwl_autoload', True):
            texroot = get_tex_root(view)
            if texroot:
                get_packages(os.path.split(texroot)[0], texroot, packages)

        if not packages:
            return

        completions = get_cwl_completions().get_completions(
            packages, environment=True
        )

        if prefix:
            completions = [c for c in completions if c[1].startswith(prefix)]

        show_entries = [c[0].split('\t') for c in completions]
        completions = [c[1] for c in completions]
        return show_entries, completions

    def matches_line(self, line):
        return bool(
            BEGIN_END_BEFORE_REGEX.match(line)
        )

    def is_enabled(self):
        return get_setting('env_auto_trigger', True)
