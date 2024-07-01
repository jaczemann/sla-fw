#!/bin/sh

set -x

export PYTHONPATH="$(pwd)$(find ./dependencies/ -maxdepth 1 -type d -printf ':%p')"

echo "Using mypy version:"
python3 -m mypy --version
python3 -m mypy slafw
