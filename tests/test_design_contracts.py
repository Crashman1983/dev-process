import hashlib
import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

REG = "docs/process/design-contracts"
CONTRACT = "docs/design/web-contract.md"
ROUND = "docs/design/concepts/web-round-1"
REVIEW = "docs/design/concepts/web-round-1-independent-review.md"
ADR = "docs/process/adr/adr-0009-web-visual-language.md"

CONTRACT_TEXT = """# Web design contract

**Status:** accepted

## 2. Screens (S*)

| S01 | Overview |

## 3.3 Elevation (E*)

| E1 | docked |

## 4. Components

### C01 Composer
- hit area 44 pt

### C02 Status pill
- AX3 reflows to two lines
"""


def _render(render, tmp_path, **mods):
    m = {"design_contracts": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _gate(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_design_contracts.py"), str(out)],
        capture_output=True, text=True)


def _seal(out: Path, *args):
    return subprocess.run([sys.executable, str(out / "scripts/process/seal.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write(out: Path, rel: str, text: str) -> Path:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _entry(out: Path, **over) -> dict:
    c = out / CONTRACT
    if not c.exists():
        _write(out, CONTRACT, CONTRACT_TEXT)
    data = {"surface": "web", "contract": CONTRACT, "status": "draft",
            "pin": f"sha256:{_sha(c)}", "id_prefixes": ["S", "C", "E", "AX"]}
    data.update(over)
    _write(out, f"{REG}/web.json", json.dumps(data))
    return data


def _accepted(out: Path, decision: str = "GO", **over) -> dict:
    _write(out, ADR, "# ADR-0009: web visual language\n\n## Status\nAccepted\n")
    _write(out, REVIEW, f"# Review\n\n**Decision:** {decision}\n")
    return _entry(out, status="accepted", adr=ADR, review=REVIEW, **over)


# --- presence ---------------------------------------------------------------

def test_module_off_absent_on_present(render, tmp_path):
    off = render(tmp_path / "off", {"project_name": "d"})
    assert not (off / "scripts/process/check_design_contracts.py").exists()
    assert not (off / "scripts/process/seal.py").exists()
    on = _render(render, tmp_path / "on")
    assert (on / "scripts/process/check_design_contracts.py").is_file()
    assert (on / "scripts/process/seal.py").is_file()
    assert (on / "docs/process/modules/design-contracts.md").is_file()
    assert (on / f"{REG}/surface.example.json").is_file()
    for t in ("surface-contract.md", "independent-review.md", "round-README.md"):
        assert (on / f"{REG}/templates/{t}").is_file()


def test_module_is_in_the_standard_set_and_missing_key_means_off(render_raw, tmp_path):
    # default answers: on. An adopter whose recorded modules mapping predates
    # the module (re-asserted as --data on update) renders with it OFF, never
    # with a crash — the documented path is to add the key to the answers.
    std = render_raw(tmp_path / "std", {"project_name": "d"})
    assert (std / "scripts/process/check_design_contracts.py").is_file()
    old = render_raw(tmp_path / "old", {"project_name": "d", "modules": {
        "speckit": False, "doc_drift_gate": False, "arch_onboarding": False,
        "feature_registry": False, "github_issues": False, "contracts": False,
        "git_hooks": False, "security_floor": False, "sbom": False,
        "telemetry": False, "arch_docs": False, "github_master": False}})
    assert not (old / "scripts/process/check_design_contracts.py").exists()
    assert "design-contracts" not in (old / "CLAUDE.md").read_text()


def test_gate_runner_runs_it(render, tmp_path):
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py"), "--all-notes"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "design-contracts: note: no design contracts yet" in r.stdout


# --- registry + pin -------------------------------------------------------------

def test_empty_registry_is_a_note(render, tmp_path):
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0 and "no design contracts yet" in r.stdout


def test_valid_draft_passes_with_draft_note(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "is a draft" in r.stdout


def test_pin_drift_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    (out / CONTRACT).write_text(CONTRACT_TEXT + "\n### C03 New thing\n")
    r = _gate(out)
    assert r.returncode == 1 and "changed without a re-pin" in r.stdout
    # opaque pin: drift degrades to a note
    _entry(out, pin="design-system:v3")
    (out / CONTRACT).write_text(CONTRACT_TEXT + "\n### C03 New thing\n")
    r = _gate(out)
    assert r.returncode == 0 and "opaque pin" in r.stdout


def test_structure_errors_are_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, f"{REG}/web.json", "{not json")
    assert _gate(out).returncode == 1
    _write(out, f"{REG}/web.json", json.dumps({"surface": "ios", "contract": CONTRACT,
                                               "status": "draft", "pin": "x",
                                               "id_prefixes": ["C"]}))
    r = _gate(out)
    assert r.returncode == 1 and "must equal the filename stem" in r.stdout
    _entry(out, status="final")
    assert "'status' must be one of" in _gate(out).stdout
    _entry(out, id_prefixes=[])
    assert "'id_prefixes'" in _gate(out).stdout
    _entry(out, contract="../outside.md")
    assert "escapes the repo root" in _gate(out).stdout
    _entry(out, contract="docs/design/missing.md")
    assert "not committed" in _gate(out).stdout


def test_duplicate_id_heading_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    c = _write(out, CONTRACT, CONTRACT_TEXT + "\n### C01 Composer again\n")
    _entry(out, pin=f"sha256:{_sha(c)}")
    r = _gate(out)
    assert r.returncode == 1 and "ID C01 is defined by 2 headings" in r.stdout


# --- accepted needs ADR + independent GO ---------------------------------------

def test_accepted_requires_adr_and_go(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, status="accepted")
    r = _gate(out)
    assert r.returncode == 1
    assert "requires 'adr'" in r.stdout and "requires 'review'" in r.stdout
    _accepted(out)
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "no sealed reference" in r.stdout
    _accepted(out, decision="NO GO")
    r = _gate(out)
    assert r.returncode == 1 and "did not clear it" in r.stdout
    _write(out, REVIEW, "# Review\n\nlooks fine\n")
    r = _gate(out)
    assert r.returncode == 1 and "records no decision line" in r.stdout
    # German decision line is read too
    _write(out, REVIEW, "# Review\n\nEntscheidung: GO mit Auflage\n")
    assert _gate(out).returncode == 0


# --- plans cite real IDs ------------------------------------------------------------

def test_plan_citing_undefined_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\ndesign-contract: web\n\nImplements C01 and E1.\n")
    assert _gate(out).returncode == 0
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\ndesign-contract: web\n\nImplements C07.\n")
    r = _gate(out)
    assert r.returncode == 1 and "cites web design-contract ID C07" in r.stdout
    # archived plans are history: never scanned
    (plans / "2026-09-15-composer.md").unlink()
    (plans / "archive").mkdir(exist_ok=True)
    (plans / "archive/2026-01-01-old.md").write_text("Implements C99.\n")
    assert _gate(out).returncode == 0
    # spec plans count as active plans
    _write(out, "specs/012-thing/plan.md", f"# Plan\n\nNorm: `{CONTRACT}`. Implements C42.\n")
    assert _gate(out).returncode == 1


def test_id_pattern_is_word_bounded(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-15-x.md").write_text("LINE1 and PRE-C77 and C-9 are not IDs.\n")
    assert _gate(out).returncode == 0


# --- seal + reference ---------------------------------------------------------------

def _round(out: Path):
    _write(out, f"{ROUND}/boards/S01-desktop-light.png", "png-bytes-1")
    _write(out, f"{ROUND}/boards/S01-desktop-dark.png", "png-bytes-2")
    _write(out, f"{ROUND}/README.md", "# round 1\n")


def test_seal_and_verify(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, CONTRACT, CONTRACT_TEXT)
    _round(out)
    r = _seal(out, "--seal", ROUND, "--dep", CONTRACT)
    assert r.returncode == 0, r.stderr
    assert "sealed 3 file(s) + 1 external dependency" in r.stdout
    manifest = json.loads((out / ROUND / "manifest.json").read_text())
    assert set(manifest["files"]) == {"boards/S01-desktop-light.png", "boards/S01-desktop-dark.png", "README.md"}
    assert manifest["external"] == {CONTRACT: _sha(out / CONTRACT)}
    seal_hex = (out / ROUND / "manifest.sha256").read_text().strip()
    assert seal_hex == hashlib.sha256((out / ROUND / "manifest.json").read_bytes()).hexdigest()
    assert _seal(out, "--verify", ROUND).returncode == 0
    # deterministic: sealing the same bytes again yields the same seal
    _seal(out, "--seal", ROUND, "--dep", CONTRACT)
    assert (out / ROUND / "manifest.sha256").read_text().strip() == seal_hex
    # an edited board: hard
    (out / ROUND / "boards/S01-desktop-light.png").write_text("tampered")
    r = _seal(out, "--verify", ROUND)
    assert r.returncode == 1 and "content differs" in r.stdout
    (out / ROUND / "boards/S01-desktop-light.png").write_text("png-bytes-1")
    # an undeclared new file: hard
    _write(out, f"{ROUND}/boards/S02-late.png", "x")
    r = _seal(out, "--verify", ROUND)
    assert r.returncode == 1 and "not in the seal" in r.stdout
    (out / ROUND / "boards/S02-late.png").unlink()
    # an edited manifest: hard
    (out / ROUND / "manifest.json").write_text("{}")
    assert _seal(out, "--verify", ROUND).returncode == 1
    _seal(out, "--seal", ROUND, "--dep", CONTRACT)
    # a drifted external dependency: exit 2, boards intact
    (out / CONTRACT).write_text(CONTRACT_TEXT + "\namended\n")
    r = _seal(out, "--verify", ROUND)
    assert r.returncode == 2 and "external drift" in r.stdout and "re-seal" in r.stdout
    # errors
    assert _seal(out, "--seal", ROUND, "--dep", "../etc/passwd").returncode == 1
    assert _seal(out, "--seal", "docs/design/concepts/nope").returncode == 1
    assert _seal(out, "--verify", "docs/design/concepts/nope").returncode == 1
    assert _seal(out).returncode == 2


def test_reference_binds_review_to_the_seal(render, tmp_path):
    out = _render(render, tmp_path)
    _round(out)
    _write(out, CONTRACT, CONTRACT_TEXT)
    assert _seal(out, "--seal", ROUND, "--dep", CONTRACT).returncode == 0
    seal_hex = (out / ROUND / "manifest.sha256").read_text().strip()
    _accepted(out, reference=ROUND)
    # review without the seal hash: a note, not red
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "does not name the seal" in r.stdout
    # review naming this seal: clean
    _write(out, REVIEW, f"# Review\n\nSeal reviewed: manifest.sha256 = `{seal_hex}`\n\n**Decision:** GO\n")
    r = _gate(out)
    assert r.returncode == 0 and "does not name the seal" not in r.stdout
    # review naming a different seal: the GO applies to other boards
    _write(out, REVIEW, f"# Review\n\nSeal: {'a' * 64}\n\nDecision: GO\n")
    r = _gate(out)
    assert r.returncode == 1 and "applies to different boards" in r.stdout
    _write(out, REVIEW, f"# Review\n\nSeal: {seal_hex}\n\nDecision: GO\n")
    # a board edited after the GO: hard
    (out / ROUND / "boards/S01-desktop-dark.png").write_text("retouched")
    r = _gate(out)
    assert r.returncode == 1 and "content differs from the seal" in r.stdout
    (out / ROUND / "boards/S01-desktop-dark.png").write_text("png-bytes-2")
    # the contract amended + re-pinned, boards untouched: external drift is a note
    c = out / CONTRACT
    c.write_text(CONTRACT_TEXT + "\n### C03 Amended\n")
    _accepted(out, reference=ROUND, pin=f"sha256:{_sha(c)}")
    _write(out, REVIEW, f"# Review\n\nSeal: {seal_hex}\n\nDecision: GO\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "rendered from an older dependency" in r.stdout
    # an unsealed reference folder: hard
    _accepted(out, reference="docs/design/concepts/web-round-2", pin=f"sha256:{_sha(c)}")
    _write(out, REVIEW, f"# Review\n\nSeal: {seal_hex}\n\nDecision: GO\n")
    (out / "docs/design/concepts/web-round-2").mkdir()
    r = _gate(out)
    assert r.returncode == 1 and "not sealed" in r.stdout


# --- in flight: a surface change must cite an ID ----------------------------------

def _git(out: Path, *args):
    return subprocess.run(["git", *args], cwd=out, capture_output=True, text=True, check=True)


def test_surface_change_without_cited_id_is_a_note(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, paths=["web/**"])
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feat")
    _write(out, "web/src/composer.css", ".c{}\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: composer")
    r = _gate(out)
    assert r.returncode == 0
    assert "touches 1 file(s) under the web surface" in r.stdout and "DoR R5" in r.stdout
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\ndesign-contract: web\n\nImplements C01.\n")
    r = _gate(out)
    assert r.returncode == 0 and "touches 1 file(s)" not in r.stdout
    # a change outside the surface's paths says nothing
    (plans / "2026-09-15-composer.md").unlink()
    _write(out, "backend/api.py", "x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: api")
    _git(out, "checkout", "-q", "main")
    _git(out, "checkout", "-q", "-b", "feat2")
    _write(out, "backend/other.py", "x = 2\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: other")
    assert "under the web surface" not in _gate(out).stdout


# --- review bundle names the governing contract ---------------------------------

def test_review_bundle_lists_contract_and_cited_ids(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feat")
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\nissue: #9\ndesign-contract: web\n\nImplements C01, E1.\n")
    _write(out, "web/src/composer.css", ".c{}\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: composer")
    r = subprocess.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"),
                        "--base", "main", "--skip-preflight"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Design contracts governing this change" in r.stdout
    assert f"**web**: `{CONTRACT}` (draft, no sealed reference) — plan cites C01, E1" in r.stdout


# --- the docs bind it ------------------------------------------------------------------

def test_dor_dod_and_checklist_bind_the_contract(render, tmp_path):
    out = _render(render, tmp_path)
    dor = (out / "docs/process/definition-of-ready-and-done.md").read_text()
    assert "contract IDs" in dor and "design-contracts" in dor
    assert "sealed reference board" in dor
    rc = (out / "docs/process/review-checklist.md").read_text()
    assert "sealed reference board" in rc
    rules = (out / "docs/process/mandatory-rules.md").read_text()
    assert "design-contracts" in rules
    assert "docs/process/modules/design-contracts.md" in (out / "CLAUDE.md").read_text()


def test_verify_reads_a_render_kits_own_manifest_shape(render, tmp_path):
    # a project's freezer writes files as [{path, sha256}] and dependencies
    # as folder-relative `../..` paths — the same seal formula; verify reads it
    out = _render(render, tmp_path)
    _write(out, CONTRACT, CONTRACT_TEXT)
    _round(out)
    rdir = out / ROUND
    manifest = {"format": 1, "generatedAt": "2026-09-14T07:40:14.008Z",
                "files": [{"path": p, "sha256": _sha(rdir / p)} for p in
                          ("README.md", "boards/S01-desktop-dark.png", "boards/S01-desktop-light.png")],
                "externalDependencies": [{"path": "../../web-contract.md", "sha256": _sha(out / CONTRACT)}]}
    text = json.dumps(manifest, indent=2) + "\n"
    (rdir / "manifest.json").write_text(text)
    (rdir / "manifest.sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "  manifest.json\n")
    assert _seal(out, "--verify", ROUND).returncode == 0
    (out / CONTRACT).write_text(CONTRACT_TEXT + "\namended\n")
    r = _seal(out, "--verify", ROUND)
    assert r.returncode == 2 and "../../web-contract.md: changed" in r.stdout
    (rdir / "boards/S01-desktop-dark.png").write_text("x")
    assert _seal(out, "--verify", ROUND).returncode == 1


def test_unbound_plan_is_a_note_and_binding_decides_the_norm(render, tmp_path):
    # ID families are shared across surfaces: an iOS plan's E1 must not be
    # judged against the web contract. A plan names the contract it means.
    out = _render(render, tmp_path)
    _entry(out)
    ios = _write(out, "docs/design/ios-contract.md", "# iOS\n\n### C01 Composer\n\n### E1 docked\n\n### E7 overlay\n")
    _write(out, f"{REG}/ios.json", json.dumps({"surface": "ios", "contract": "docs/design/ios-contract.md",
                                              "status": "draft", "pin": f"sha256:{_sha(ios)}",
                                              "id_prefixes": ["C", "E"]}))
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    p = plans / "2026-09-15-composer.md"
    p.write_text("# Plan\n\ntier: 2\n\nImplements E7.\n")  # unbound: web has no E7
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "names no design contract" in r.stdout and "design-contract: ios|web" in r.stdout
    p.write_text("# Plan\n\ntier: 2\ndesign-contract: ios\n\nImplements E7.\n")
    r = _gate(out)
    assert r.returncode == 0 and "names no design contract" not in r.stdout
    p.write_text("# Plan\n\ntier: 2\ndesign-contract: web\n\nImplements E7.\n")
    r = _gate(out)
    assert r.returncode == 1 and "cites web design-contract ID E7" in r.stdout
    assert "ios design-contract" not in r.stdout


def test_zero_padding_does_not_split_an_id(render, tmp_path):
    out = _render(render, tmp_path)
    c = _write(out, CONTRACT, CONTRACT_TEXT + "\n### C01 Composer (again, as C1)\n")
    _entry(out, pin=f"sha256:{_sha(c)}")
    r = _gate(out)
    assert r.returncode == 1 and "ID C01 is defined by 2 headings" in r.stdout
    _write(out, CONTRACT, CONTRACT_TEXT)
    _entry(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-15-x.md").write_text("# Plan\n\ndesign-contract: web\n\nImplements C1 and C2 (P4 delta C1–C2).\n")
    assert _gate(out).returncode == 0


def test_review_reading_is_strict_about_decisions_and_seals(render, tmp_path):
    out = _render(render, tmp_path)
    # a fenced example does not decide; the last decision line stands
    _accepted(out)
    _write(out, REVIEW, "# R\n\n```\nDecision: GO\n```\n\nDecision: NO GO\n")
    r = _gate(out)
    assert r.returncode == 1 and "did not clear it" in r.stdout
    _write(out, REVIEW, "# R\n\nDecision: GO/NO-GO meeting on Friday\n")
    r = _gate(out)
    assert r.returncode == 1 and "records no decision line" in r.stdout
    # a review-artifact digest is not "a different seal": only a labelled seal line counts
    _round(out)
    _write(out, CONTRACT, CONTRACT_TEXT)
    assert _seal(out, "--seal", ROUND, "--dep", CONTRACT).returncode == 0
    seal_hex = (out / ROUND / "manifest.sha256").read_text().strip()
    _accepted(out, reference=ROUND)
    _write(out, REVIEW, f"# R\n\nArtifact digest: {'6' * 64}\n\nDecision: GO\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "does not name the seal" in r.stdout
    _write(out, REVIEW, f"# R\n\nArtifact digest: {'6' * 64}\nmanifest.sha256: {seal_hex}\n\nDecision: GO\n")
    r = _gate(out)
    assert r.returncode == 0 and "does not name the seal" not in r.stdout


def test_subheading_mentioning_an_id_is_not_a_second_definition(render, tmp_path):
    out = _render(render, tmp_path)
    c = _write(out, CONTRACT, CONTRACT_TEXT + "\n#### Notes on C01 spacing\n\n```\n### C01 quoted example\n```\n")
    _entry(out, pin=f"sha256:{_sha(c)}")
    assert _gate(out).returncode == 0


def test_nested_manifest_names_are_content(render, tmp_path):
    out = _render(render, tmp_path)
    _write(out, CONTRACT, CONTRACT_TEXT)
    _round(out)
    _write(out, f"{ROUND}/boards/sub/manifest.json", "{}")
    assert _seal(out, "--seal", ROUND).returncode == 0
    _write(out, f"{ROUND}/boards/sub/manifest.json", "{\"edited\": 1}")
    r = _seal(out, "--verify", ROUND)
    assert r.returncode == 1 and "content differs" in r.stdout
    _write(out, f"{ROUND}/boards/sub/manifest.sha256", "x")
    assert "not in the seal" in _seal(out, "--verify", ROUND).stdout


def test_notes_only_cite_the_current_seal_or_explicit_history(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    _write(out, ROUND + '/board.svg', '<svg/>\n')
    assert _seal(out, '--seal', ROUND, '--dep', CONTRACT).returncode == 0
    current = (out / ROUND / 'manifest.sha256').read_text().split()[0]
    _entry(out, reference=ROUND, notes='manifest.sha256 = ' + 'f' * 64)
    r = _gate(out)
    assert r.returncode == 1 and 'notes' in r.stdout and 'historical' in r.stdout
    _entry(out, reference=ROUND, notes=f'Current manifest.sha256 = {current[:12]}')
    assert _gate(out).returncode == 0
    _entry(out, reference=ROUND, notes='historical manifest.sha256 = ' + 'f' * 64)
    assert _gate(out).returncode == 0


def test_a_notes_sidecar_is_read_with_the_entry_and_merges_by_union(render, tmp_path):
    """Kenni #2588: amendments go into `<surface>.notes.md` as whole lines — two
    branches appending to it merge without a conflict; the gate reads both texts."""
    out = _render(render, tmp_path)
    _entry(out)
    _write(out, ROUND + '/board.svg', '<svg/>\n')
    assert _seal(out, '--seal', ROUND, '--dep', CONTRACT).returncode == 0
    _entry(out, reference=ROUND, notes='Plain prose.')
    assert _gate(out).returncode == 0  # no sidecar: no finding
    _write(out, f"{REG}/web.notes.md", "2026-10-15: amended, manifest.sha256 = " + "f" * 64 + "\n")
    r = _gate(out)
    assert r.returncode == 1 and 'notes' in r.stdout and 'historical' in r.stdout
    _write(out, f"{REG}/web.notes.md", "2026-10-15: historical manifest.sha256 = " + "f" * 64 + "\n")
    assert _gate(out).returncode == 0
    assert "*.notes.md merge=union" in (out / REG / ".gitattributes").read_text()
    assert "/inbox.md merge=union" in (out / ".process-work/.gitattributes").read_text()


# --- declaring the contract (#248, downstream Kenni #1914): opt-in duty ----------

DECL = "docs/process/design-contract-declaration.local.json"
PLAN = ".process-work/plans/2026-10-15-77-widget.md"


def _git(out: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(out), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _declared_repo(render, tmp_path, rule: dict | None = None) -> Path:
    """main carries the duty (or none) and a draft `web` contract; work goes on `feature`."""
    out = _render(render, tmp_path)
    _entry(out)
    if rule is not None:
        _write(out, DECL, json.dumps(rule))
    _git(out, "init", "-q", "-b", "main")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    return out


def _plan(out: Path, body: str, rel: str = PLAN, *, commit_day: str | None = None) -> None:
    _write(out, rel, "# Plan\n\ntier: 2\nissue: #77\n\n" + body)
    if commit_day:
        _git(out, "add", "-A")
        env = {**os.environ, "GIT_AUTHOR_DATE": f"{commit_day}T12:00:00", "GIT_COMMITTER_DATE": f"{commit_day}T12:00:00"}
        subprocess.run(["git", "-C", str(out), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                        "-m", "plan"], env=env, check=True)


@pytest.mark.parametrize("body,needle", [
    ("", "no `design-contract:` line"),
    ("design-contract: n/a\n", "without a reason"),
    ("design-contract: mobile\n", "unknown design contract `mobile`"),
    ("design-contract: web\n", "`## Design Contract Trace` is missing or empty"),
    ("design-contract: web\n\n## Design Contract Trace\n\n## Next\n", "missing or empty"),
])
def test_under_the_duty_a_plan_states_its_contract(render, tmp_path, body, needle):
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _plan(out, body)
    r = _gate(out)
    assert r.returncode == 1 and needle in r.stdout, r.stdout


@pytest.mark.parametrize("body", ["design-contract: n/a — no screen changes\n",
                                  "design-contract: web\n\n## Design Contract Trace\n\nS01 header, C02 pill.\n"])
def test_a_stated_contract_satisfies_the_duty(render, tmp_path, body):
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _plan(out, body)
    assert _gate(out).returncode == 0, _gate(out).stdout


def test_without_the_duty_nothing_changes(render, tmp_path):
    out = _declared_repo(render, tmp_path)
    _plan(out, "")  # no line at all: fine, as before
    assert _gate(out).returncode == 0


def test_a_plan_from_before_the_day_is_a_note_and_a_backdated_name_proves_nothing(render, tmp_path):
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _git(out, "checkout", "-q", "main")
    _plan(out, "", rel=".process-work/plans/2026-09-01-old.md", commit_day="2026-09-02")
    _git(out, "checkout", "-q", "feature")
    _git(out, "merge", "-q", "--no-edit", "main")
    r = _gate(out)
    assert r.returncode == 0 and "predate the declaration duty" in r.stdout, r.stdout
    # a plan named for an old day but added now is bound
    _plan(out, "", rel=".process-work/plans/2026-08-01-backdated.md")
    r = _gate(out)
    assert r.returncode == 1 and "2026-08-01-backdated.md: no `design-contract:` line" in r.stdout, r.stdout


def test_a_backdated_commit_on_the_branch_is_still_bound(render, tmp_path):
    """Refute v2.74: an author date before the day grandfathered a plan this branch adds."""
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _plan(out, "", rel=".process-work/plans/2026-01-01-sneaky.md", commit_day="2026-01-01")
    r = _gate(out)
    assert r.returncode == 1 and "sneaky.md: no `design-contract:` line" in r.stdout, r.stdout


@pytest.mark.parametrize("body,ok", [
    ("design-contract: `web`\n\n## Design Contract Trace\n\nS01.\n", True),
    ("design-contract: Web\n\n## Design Contract Trace\n\nS01.\n", True),
    ("design-contract: n/a:\n", False),
    ("- step\n\n  ```\n  design-contract: n/a — example only\n  ```\n", False),
    ("    ```\n    design-contract: n/a — indented example\n    ```\n", False),
    ("````\nx\n`````\n\ndesign-contract: n/a — real one after a longer close\n", True),
])
def test_the_declaration_is_read_as_binding_and_fences_are(render, tmp_path, body, ok):
    """Refute v2.74: one reader for the line (as `bound_to`), fences as the review gate reads them."""
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _plan(out, body)
    r = _gate(out)
    assert (r.returncode == 0) is ok, r.stdout


def test_spec_plans_bind_above_the_spec_number(render, tmp_path):
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01", "spec_above": 5})
    _plan(out, "", rel="specs/0005-old/plan.md")
    assert _gate(out).returncode == 0
    _plan(out, "", rel="specs/0006-new/plan.md")
    r = _gate(out)
    assert r.returncode == 1 and "specs/0006-new/plan.md" in r.stdout, r.stdout


def test_a_branch_cannot_lift_the_duty_for_itself(render, tmp_path):
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _git(out, "rm", "-q", DECL)
    _git(out, "commit", "-q", "-m", "chore: drop the duty")
    _plan(out, "")
    r = _gate(out)
    assert r.returncode == 1 and "no `design-contract:` line" in r.stdout, r.stdout  # the fork point has it


def test_a_malformed_duty_is_named(render, tmp_path):
    out = _declared_repo(render, tmp_path, {"from": "October"})
    r = _gate(out)
    assert r.returncode == 1 and 'needs "from": "YYYY-MM-DD"' in r.stdout, r.stdout


def test_the_duty_file_is_no_registry_entry(render, tmp_path):
    """Plan review v2.74: inside the registry folder it would be read as a broken surface."""
    out = _render(render, tmp_path)
    _write(out, DECL, json.dumps({"from": "2026-10-01"}))
    r = _gate(out)
    assert r.returncode == 0 and "no design contracts yet" in r.stdout, r.stdout


def test_an_ambiguous_fork_point_does_not_crash_a_project_without_the_duty(render, tmp_path):
    """Refute v2.74: `merge_base` raised before the opt-in file was even read."""
    out = _declared_repo(render, tmp_path)
    _write(out, "f0.txt", "x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feature work")
    _git(out, "checkout", "-q", "main")
    _write(out, "m.txt", "m\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main moves")
    _git(out, "merge", "-q", "--no-edit", "feature")
    _git(out, "checkout", "-q", "feature")
    _write(out, "f.txt", "f\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feature moves")
    _git(out, "merge", "-q", "--no-edit", "main~1")
    r = _gate(out)
    assert "Traceback" not in r.stderr and r.returncode == 0, r.stderr + r.stdout


def test_a_renamed_old_plan_keeps_its_age(render, tmp_path):
    """Delta review v2.74: a plan from before the day, renamed on the branch, became bound."""
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _git(out, "checkout", "-q", "main")
    _plan(out, "", rel=".process-work/plans/2026-09-01-old.md", commit_day="2026-09-02")
    _git(out, "checkout", "-q", "feature")
    _git(out, "merge", "-q", "--no-edit", "main")
    _git(out, "mv", ".process-work/plans/2026-09-01-old.md", ".process-work/plans/2026-09-01-old-renamed.md")
    _git(out, "commit", "-q", "-m", "rename")
    r = _gate(out)
    assert r.returncode == 0 and "predate the declaration duty" in r.stdout, r.stdout


def test_an_info_string_fence_line_closes_nothing(render, tmp_path):
    """Delta review v2.74: ```python inside a fence closed it (CommonMark: a closing fence has no info)."""
    out = _declared_repo(render, tmp_path, {"from": "2026-10-01"})
    _plan(out, "```text\n```python\n```\n\ndesign-contract: n/a — no screen\n")
    assert _gate(out).returncode == 0, _gate(out).stdout
