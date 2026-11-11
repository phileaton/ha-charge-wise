#!/bin/bash

# script/hooks/clean.pre.sh: Remove integration installs from the active environment without requiring pip.

for integration_dir in custom_components/*; do
    if [[ ! -d "$integration_dir" || -L "$integration_dir" ]]; then
        continue
    fi
    integration_package="${integration_dir##*/}"
    if uv pip show --python "$VIRTUAL_ENV/bin/python" "$integration_package" >/dev/null 2>&1; then
        log_info "Removing installed integration: $integration_package"
        uv pip uninstall --python "$VIRTUAL_ENV/bin/python" "$integration_package"
    fi
done
