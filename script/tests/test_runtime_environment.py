"""Regression tests for development environment activation and cleanup."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize("active", [False, True])
def test_activation_repairs_inherited_path(tmp_path: Path, *, active: bool) -> None:
    """An inherited environment variable must not leave system Python selected."""
    venv = tmp_path / "venv"
    binary = venv / "bin"
    binary.mkdir(parents=True)
    for name in ("python", "python3"):
        executable = binary / name
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    (binary / "activate").write_text('export PATH="$VIRTUAL_ENV/bin:$PATH"\n', encoding="utf-8")
    environment = {**os.environ, "VIRTUAL_ENV": str(venv), "PATH": "/usr/bin:/bin"}
    if active:
        environment["PATH"] = f"{binary}:{environment['PATH']}"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; activate_venv; command -v python; command -v python3',
            "--",
            str(ROOT / "script/.lib/output.sh"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-2:] == [str(binary / "python"), str(binary / "python3")]


@pytest.mark.unit
def test_cleanup_targets_active_environment_without_pip(tmp_path: Path) -> None:
    """Cleanup removes installed integrations using the explicitly selected Python."""
    components = tmp_path / "custom_components"
    (components / "charge_wise").mkdir(parents=True)
    (components / "linked").symlink_to(components / "charge_wise", target_is_directory=True)
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$UV_CALL_LOG"\n', encoding="utf-8")
    uv.chmod(0o755)
    call_log = tmp_path / "uv.log"
    venv = tmp_path / "venv"
    result = subprocess.run(
        ["bash", "-c", 'log_info() { :; }; source "$1"', "--", str(ROOT / "script/hooks/clean.pre.sh")],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{binary}:/usr/bin:/bin", "VIRTUAL_ENV": str(venv), "UV_CALL_LOG": str(call_log)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert call_log.read_text(encoding="utf-8").splitlines() == [
        f"pip show --python {venv}/bin/python charge_wise",
        f"pip uninstall --python {venv}/bin/python charge_wise",
    ]
