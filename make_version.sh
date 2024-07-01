#!/bin/sh

OUT="slafw/__init__.py"

echo "__package_version__ = '`git describe --abbrev=0`'" > $OUT
echo "__full_version__ = '`./version.sh`'" >> $OUT
