"""SP67: byte-identical screenshots under different names are evidence of
nothing — a ratchet with a baseline pin."""
import subprocess
import sys


def _run(root, *args):
    return subprocess.run([sys.executable, str(root / "scripts/process/check_baseline_duplicates.py"),
                           *args], cwd=root, capture_output=True, text=True)


def _shots(root):
    d = root / "e2e/__screenshots__"
    d.mkdir(parents=True)
    (d / "home-desktop-light.png").write_bytes(b"\x89PNG A")
    (d / "home-mobile-light.png").write_bytes(b"\x89PNG A")     # desktop minted as mobile
    (d / "home-desktop-dark.png").write_bytes(b"\x89PNG B")
    (root / "e2e/other").mkdir()
    (root / "e2e/other/home-desktop-light.png").write_bytes(b"\x89PNG A")  # same NAME elsewhere: fine
    return d


def test_identical_images_under_different_names_fail(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _shots(out)
    r = _run(out, "e2e")
    assert r.returncode == 1
    assert "home-mobile-light.png" in r.stdout and "evidence of what its name claims" in r.stdout
    assert "FAILED (1 new" in r.stdout


def test_ratchet_pins_then_only_shrinks(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    d = _shots(out)
    pin = out / "docs/design/baseline-duplicates.txt"
    assert _run(out, "--write-baseline", str(pin), "e2e").returncode == 0
    assert _run(out, "--baseline", str(pin), "e2e").returncode == 0  # pinned passes
    (d / "home-desktop-dark.png").write_bytes(b"\x89PNG A")            # a NEW group member
    r = _run(out, "--baseline", str(pin), "e2e")
    assert r.returncode == 1 and "new" in r.stdout
    (d / "home-mobile-light.png").write_bytes(b"\x89PNG C")            # fixed the pinned one
    (d / "home-desktop-dark.png").write_bytes(b"\x89PNG B")
    r = _run(out, "--baseline", str(pin), "e2e")
    assert r.returncode == 1 and "no longer occurs" in r.stdout        # stale pin must go


def test_usage_and_missing_dir(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert _run(out).returncode == 2
    assert _run(out, "nope").returncode == 2
