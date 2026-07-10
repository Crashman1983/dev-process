"""One-owner tripwires: duplicates that CANNOT be imports (independent render
units) are pinned here so silent drift fails the template suite.

Render-unit rule: a module script may import core scripts and same-module
siblings, never another optional module — the other module may not be rendered.
Where that blocks consolidation, the copy stays and this file pins it.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "template/scripts/process"


def _src(name: str) -> str:
    return (TEMPLATE / name).read_text(encoding="utf-8")


def _fn_body(src: str, fn: str) -> str:
    """The exact text of a top-level `def fn(...)` block."""
    m = re.search(rf"(?ms)^def {fn}\(.*?(?=^\S|\Z)", src)
    assert m, f"def {fn} not found"
    return m.group(0).rstrip()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def test_tracked_files_helpers_identical_sbom_vs_security_floor():
    # sbom and security_floor are independent optional modules — neither may
    # import the other, so the git-ls-files+fnmatch helper is duplicated by
    # design. Byte-identical bodies, or this trips.
    sbom = _src("{% if modules.sbom %}check_sbom.py{% endif %}")
    floor = _src("{% if modules.security_floor %}check_security_floor.py{% endif %}.jinja")
    for fn in ("_tracked_files", "_matches_any"):
        assert _fn_body(sbom, fn) == _fn_body(floor, fn), (
            f"{fn} drifted between check_sbom and check_security_floor — "
            f"keep the twins byte-identical (independent render units)")


def test_dor_heuristic_agrees_attention_vs_gh_sync(render, tmp_path):
    # github_issues (attention.py) and github_master (gh_sync.py) are
    # independent modules; both derive the same EARS/epic DoR facts "in sync
    # by convention". This pins the convention with shared fixtures.
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"github_issues": True,
                                        "github_master": True}})
    att = _load(out / "scripts/process/attention.py", "att_mod")
    sync = _load(out / "scripts/process/gh_sync.py", "sync_mod")

    cases = [
        # (labels, title, body)
        ([{"name": "type:feature"}], "Widget", "## Acceptance criteria (EARS)\nWHEN x the system shall y"),
        ([{"name": "type:feature"}], "Widget", "The system shall respond."),
        ([{"name": "type:feature"}], "Widget", "free prose, no EARS"),
        ([{"name": "type:epic"}], "Big theme", ""),
        ([], "EPIC: rollout", "no criteria"),
        ([{"name": "type:bug"}], "Fix", "### Akzeptanzkriterien (EARS)\n..."),
        ([], "Widget", None),
    ]
    for labels, title, body in cases:
        names = {lab["name"] for lab in labels}
        facts = sync._dor_facts(labels, title, body)
        assert facts["ears"] == (att._is_epic(names, title) or att._has_ears(body)), (
            f"EARS/epic verdict drifted for {title!r}/{body!r}")


def test_adapters_list_every_module_doc():
    # the _mod_slugs map in each harness adapter must name all modules —
    # a missing key means an active gate whose doc the agent is never told
    # to read (found live: sbom was missing in all three adapters)
    import yaml
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    modules = set(re.findall(r"([a-z_]+):", copier["modules"]["default"]))
    assert len(modules) >= 13, "copier modules default not parsed"
    adapters = [
        ROOT / "template/CLAUDE.md.jinja",
        ROOT / "template/.github/{% if harnesses.copilot %}copilot-instructions.md{% endif %}.jinja",
        ROOT / "template/{% if harnesses.agents_md %}AGENTS.md{% endif %}.jinja",
    ]
    for p in adapters:
        src = p.read_text(encoding="utf-8")
        m = re.search(r"_mod_slugs\s*=\s*\{(.*?)\}", src, re.S)
        assert m, f"{p.name}: no _mod_slugs map"
        listed = set(re.findall(r'"([a-z_]+)":', m.group(1)))
        assert listed == modules, (
            f"{p.name}: _mod_slugs != copier.yml modules — "
            f"missing {sorted(modules - listed)}, extra {sorted(listed - modules)}")


def test_finding_line_regex_pinned_trace_vs_check_issues():
    # trace.py (core) cannot import the github_issues module — its FINDING
    # detection regex is a deliberate twin of check_issues' _FINDING_LINE;
    # byte-identical literals, or this trips.
    trace = _src("trace.py")
    issues = _src("{% if modules.github_issues %}check_issues.py{% endif %}.jinja")
    pat = re.compile(r'_FINDING(?:_LINE)?\s*=\s*re\.compile\(\s*r"([^"]+)"')
    m_t, m_i = pat.search(trace), pat.search(issues)
    assert m_t and m_i, "FINDING regex literal not found"
    assert m_t.group(1) == m_i.group(1), (
        f"FINDING detection drifted: trace={m_t.group(1)!r} "
        f"check_issues={m_i.group(1)!r}")
