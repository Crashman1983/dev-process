import hashlib
import json
import subprocess
import sys
from pathlib import Path

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
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\n\nImplements C01 and E1.\n")
    assert _gate(out).returncode == 0
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\n\nImplements C07.\n")
    r = _gate(out)
    assert r.returncode == 1 and "cites web design-contract ID C07" in r.stdout
    # archived plans are history: never scanned
    (plans / "2026-09-15-composer.md").unlink()
    (plans / "archive").mkdir(exist_ok=True)
    (plans / "archive/2026-01-01-old.md").write_text("Implements C99.\n")
    assert _gate(out).returncode == 0
    # spec plans count as active plans
    _write(out, "specs/012-thing/plan.md", "# Plan\n\nImplements C42.\n")
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
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\n\nImplements C01.\n")
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
    (plans / "2026-09-15-composer.md").write_text("# Plan\n\ntier: 2\nissue: #9\n\nImplements C01, E1.\n")
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
