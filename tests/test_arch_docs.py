import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

OVERVIEW = "ARCHITECTURE-OVERVIEW.md"
ADR_DIR = "docs/process/adr"


def _render(render, tmp_path, **mods):
    m = {"arch_docs": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _gate(out: Path, root: Path | None = None):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_arch_docs.py"),
         str(root if root is not None else out)],
        capture_output=True, text=True,
    )


def test_module_on_ships_scaffold_gate_doc(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / OVERVIEW).is_file()
    assert (out / "scripts/process/check_arch_docs.py").is_file()
    assert (out / "docs/process/modules/arch-docs.md").is_file()


def test_overview_renders_project_name_no_jinja_leak(render, tmp_path):
    # the scaffold must carry the .jinja suffix so its title renders, not ship
    # a raw {{ project_name }} token.
    out = render(tmp_path, {"project_name": "Acme", "modules": {"arch_docs": True}})
    text = (out / OVERVIEW).read_text(encoding="utf-8")
    assert "{{" not in text and "{%" not in text
    assert "Acme" in text


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / OVERVIEW).exists()
    assert not (out / "scripts/process/check_arch_docs.py").exists()
    assert not (out / "docs/process/modules/arch-docs.md").exists()


def test_answers_records_arch_docs(render, tmp_path):
    out = _render(render, tmp_path)
    assert "arch_docs: true" in (out / ".copier-answers.yml").read_text()


def test_seed_passes_with_placeholder_note(render, tmp_path):
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "arch-docs: OK" in r.stdout
    # the shipped scaffold is all placeholders -> a visible note, not a pass-as-done
    assert "still placeholder" in r.stdout


def test_dead_adr_reference_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    (out / OVERVIEW).write_text(
        "# Overview\n\n## 6. Decisions\n\nSee ADR-0777 for the boundary.\n",
        encoding="utf-8",
    )
    r = _gate(out)
    assert r.returncode == 1
    assert "ADR-0777" in r.stdout


def test_resolving_adr_reference_passes(render, tmp_path):
    out = _render(render, tmp_path)
    adr = out / ADR_DIR
    adr.mkdir(parents=True, exist_ok=True)
    (adr / "adr-0007-pick-a-store.md").write_text("# ADR-0007\n", encoding="utf-8")
    # ADR-7 resolves to adr-0007 via the zero-pad-insensitive lookup
    (out / OVERVIEW).write_text(
        "# Overview\n\n## 6. Decisions\n\nSee ADR-0007 and ADR-7 for the store.\n",
        encoding="utf-8",
    )
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_short_form_dead_adr_hard_fails(render, tmp_path):
    # a 1-2 digit dead ref must be caught, not silently skipped by the regex
    out = _render(render, tmp_path)
    (out / OVERVIEW).write_text(
        "# Overview\n\n## 6. Decisions\n\nSee ADR-5 for the boundary.\n",
        encoding="utf-8",
    )
    r = _gate(out)
    assert r.returncode == 1
    assert "ADR-5" in r.stdout


def test_non_utf8_overview_fails(render, tmp_path):
    out = _render(render, tmp_path)
    (out / OVERVIEW).write_bytes(b"\xff\xfe not utf8")
    r = _gate(out)
    assert r.returncode == 1
    assert "UTF-8" in r.stdout


def test_absent_overview_is_soft(render, tmp_path):
    out = _render(render, tmp_path)  # renders the gate script
    empty = tmp_path / "empty_root"
    empty.mkdir()
    r = _gate(out, root=empty)
    assert r.returncode == 0, r.stdout
    assert "no ARCHITECTURE-OVERVIEW.md yet" in r.stdout


def test_gate_runner_lists_arch_docs(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "arch-docs" in r.stdout


def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [OVERVIEW, "scripts/process/check_arch_docs.py",
                "docs/process/modules/arch-docs.md"]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "arch_docs": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
