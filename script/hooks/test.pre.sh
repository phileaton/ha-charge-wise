#!/bin/bash

# script/hooks/test.pre.sh: Run tests with the Home Assistant version required by their fixtures.

charge_wise_test_venv="$PWD/.local/ha-test-venv"
if [[ ! -x "$charge_wise_test_venv/bin/python" ]]; then
    uv venv "$charge_wise_test_venv"
fi
uv pip install --python "$charge_wise_test_venv/bin/python" --quiet \
    --requirement requirements_test.txt --requirement requirements.txt
export VIRTUAL_ENV="$charge_wise_test_venv"
activate_venv
unset charge_wise_test_venv
