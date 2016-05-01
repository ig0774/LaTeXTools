@set D=%~dp0
@set DIR=%D:~0,-1%
@pandoc -f markdown_github+yaml_metadata_block -t json %DIR%\..\README.markdown %DIR%\metadata.yaml | python %DIR%\readme-filter.py | pandoc -f json -H %DIR%\header-include.tex -V colorlinks=true --listings -o %DIR%\..\README.pdf
