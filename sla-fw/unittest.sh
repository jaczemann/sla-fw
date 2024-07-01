#!/bin/sh

set -x

export PATH="${PATH}:$(pwd)"
export PYTHONPATH="${PYTHONPATH}:$(pwd)$(find ./dependencies/ -maxdepth 1 -type d -printf ':%p')"

if ! command -v SLA-control-01.elf
then
    echo "SLA-control-01.elf not found. Did you forgot to run build_sim.sh?"
    exit 2
fi

python3-coverage run -m unittest discover --failfast --verbose --buffer slafw.tests.unittests &&
python3-coverage report --include "slafw*"
