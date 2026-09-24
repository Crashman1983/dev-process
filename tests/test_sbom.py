"""The repo SBOM and the rendered license are derived files: they must match their source."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_sbom_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_sbom.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_cyclonedx_names_every_locked_package_and_the_vendored_files():
    bom = json.loads((ROOT / "docs" / "sbom.cdx.json").read_text(encoding="utf-8"))
    assert bom["bomFormat"] == "CycloneDX"
    purls = {c.get("purl") for c in bom["components"]}
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert "pkg:pypi/copier@" + lock.split('name = "copier"\nversion = "')[1].split('"')[0] in purls
    files = [c for c in bom["components"] if c["type"] == "file"]
    assert {c["licenses"][0]["license"]["id"] for c in files} == {"MIT"}
    for c in files:
        assert (ROOT / c["bom-ref"].removeprefix("file:")).is_file()


def test_rendered_license_is_the_repo_license():
    # Apache-2.0 asks redistributors to pass the license on; every rendered repo
    # carries it next to the NOTICE that scopes it to the process files.
    ours = (ROOT / "LICENSE").read_text(encoding="utf-8")
    shipped = (ROOT / "template" / "docs" / "process" / "LICENSE").read_text(encoding="utf-8")
    assert ours == shipped
    notice = (ROOT / "template" / "docs" / "process" / "NOTICE.md").read_text(encoding="utf-8")
    assert "Apache License, Version 2.0" in notice
