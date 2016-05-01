#!/bin/sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
chmod +x $DIR/readme-filter.py
pandoc -f markdown_github+yaml_metadata_block -H $DIR/header-include.tex -V colorlinks=true -F $DIR/readme-filter.py -o $DIR/../README.pdf --listings $DIR/../README.markdown $DIR/metadata.yaml
