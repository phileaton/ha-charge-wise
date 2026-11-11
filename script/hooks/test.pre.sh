#!/bin/bash
if [[ ${CHARGE_WISE_COOLDOWN_TEST_ENV:-} == 1 ]]; then
    uv venv /tmp/charge-wise-cooldown-tests
    uv pip install --python /tmp/charge-wise-cooldown-tests/bin/python -r requirements_test.txt -r requirements_dev.txt
    uv pip install --python /tmp/charge-wise-cooldown-tests/bin/python 'homeassistant==2026.10.4'
    export VIRTUAL_ENV=/tmp/charge-wise-cooldown-tests
    activate_venv
fi
