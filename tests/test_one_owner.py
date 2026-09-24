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





def test_adapters_list_every_module_doc():
    # the _mod_slugs map in each harness adapter must name all modules —
    # a missing key means an active gate whose doc the agent is never told
    # to read (found live: sbom was missing in all three adapters)
    import yaml
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    modules = set(re.findall(r"([a-z_]+):", copier["modules"]["default"]))
    assert len(modules) >= 8, "copier modules default not parsed"
    adapters = [
        ROOT
        / "template/{% if harnesses.claude %}CLAUDE.md{% endif %}.jinja",
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



def test_no_brace_pair_in_python_templates_renders_away():
    # a Python f-string's `{{…}}` escape inside a *.py.jinja file is Jinja
    # syntax: it renders to nothing (observed: `f"{ref}^{{commit}}"` became
    # `f"{ref}^"`, the parent commit, and every push with history was refused).
    # Template expressions here use `{{ name }}` with spaces; anything else is
    # this mistake.
    offenders = []
    for p in (q for q in (ROOT / "template").rglob("*.jinja") if ".py" in q.name):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\{\{[^ {]", line):
                offenders.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, offenders
