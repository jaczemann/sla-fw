#!/bin/sh

# usage:
# all tests: ./integrationtest.sh
# one test: ./integrationtest.sh test_pages.TestIntegrationPages.test_factory_reset_factory_kit

set -x

if [ -z "$1" ]
then
    ARGS=""
else
    ARGS="slafw.tests.integration.$1"
fi

export PATH="${PATH}:$(pwd)"
export PYTHONPATH="$(pwd)$(find ./dependencies/ -maxdepth 1 -type d -printf ':%p')"

if ! command -v SLA-control-01.elf
then
    echo "SLA-control-01.elf not found. Did you forgot to run build_sim.sh?"
    exit 2
fi

python3 -m unittest discover --failfast --verbose --buffer slafw.tests.integration $ARGS &&
python3 -m unittest discover --failfast --verbose slafw.tests.virtual
