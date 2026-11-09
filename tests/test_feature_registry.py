"""feature-inventory gate (lean pass): capability -> acceptance -> proving
tests; the work-log axis (status, blocked_by, parent) moved to GitHub."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REG = "docs/process/feature-registry"


def _render(render, tmp_path, **extra):
    return render(tmp_path, {"project_name": "d", "modules": {"feature_registry": True}, **extra})


def _gate(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_feature_registry.py"), "."],
        cwd=out, capture_output=True, text=True)


def _entry(out, name="STORY-0002.json", **over):
    d = out / REG
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "id": "STORY-0002",
        "title": "Widget capability",
        "story": "As a user, when saving, the system shall persist the widget.",
        "acceptance": [{"id": "AC1", "text": "Saved widgets survive a restart."}],
        "tests": ["tests/test_widget.py"],
    }
    data.update(over)
    (d / name).write_text(json.dumps(data), encoding="utf-8")
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_widget.py").write_text("def test_widget(): pass\n")


def test_empty_inventory_is_note_not_failure(render, tmp_path):
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no inventory entries yet" in r.stdout


def test_valid_entry_passes(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_tests_is_hard(render, tmp_path):
    # an inventory entry without a proving test is a claim, not an inventory
    out = _render(render, tmp_path)
    _entry(out, tests=[])
    r = _gate(out)
    assert r.returncode == 1
    assert "non-empty list" in r.stdout


def test_dead_test_path_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, tests=["tests/test_missing.py"])
    r = _gate(out)
    assert r.returncode == 1
    assert "does not exist" in r.stdout


def test_retired_worklog_fields_are_hard(render, tmp_path):
    # status/blocked_by/parent moved to GitHub — a leftover is double bookkeeping
    out = _render(render, tmp_path)
    _entry(out, status="done", blocked_by=["STORY-0001"])
    r = _gate(out)
    assert r.returncode == 1
    assert "retired work-log field" in r.stdout
    assert "GitHub" in r.stdout


def test_duplicate_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, name="STORY-0002.json")
    _entry(out, name="STORY-0002-copy.json")
    r = _gate(out)
    assert r.returncode == 1
    assert "duplicate id" in r.stdout


def test_dangling_adr_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, adr="ADR-9999")
    r = _gate(out)
    assert r.returncode == 1
    assert "no file under" in r.stdout


def test_empty_acceptance_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, acceptance=[])
    r = _gate(out)
    assert r.returncode == 1


def test_pytest_node_selector_is_stripped(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, tests=["tests/test_widget.py::test_widget"])
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_example_seed_is_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / REG / "STORY-0001.example.json").is_file()
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_unknown_field_is_note_only(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, owner="somebody")
    r = _gate(out)
    assert r.returncode == 0
    assert "unknown field" in r.stdout


def test_invalid_json_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / REG
    d.mkdir(parents=True, exist_ok=True)
    (d / "STORY-0003.json").write_text("{ nope", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout


def test_module_doc_states_inventory_split(render, tmp_path):
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/feature-registry.md").read_text()
    assert "Inventory, not work log" in doc
    assert "GitHub" in doc
    # story_order was retired with the work-log axis
    assert not (out / "scripts/process/story_order.py").exists()


# --- v2.92 K0: one owner of configuration and loader (registry_config) ---

LOCAL = "docs/process/feature-registry.local.json"


def _local(out, data):
    (out / LOCAL).write_text(json.dumps(data), encoding="utf-8")


def test_registry_config_is_core(render, tmp_path):
    # Wächter: rendered without the module too — two core gates import it
    out = render(tmp_path, {"project_name": "d"})
    assert (out / "scripts/process/registry_config.py").is_file()
    assert (out / "docs/process/feature-registry.json").is_file()
    assert not (out / "scripts/process/check_feature_registry.py").exists()


def test_local_retired_fields_replace_the_default_list(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"retired_fields": ["blocked_by"]})
    _entry(out, parent="STORY-0001")  # retired by default, not by the project's list
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    _entry(out, blocked_by=["STORY-0001"])
    r = _gate(out)
    assert r.returncode == 1 and "retired work-log field(s) ['blocked_by']" in r.stdout, r.stdout


def test_unknown_config_key_is_hard(render, tmp_path):
    # a typo must not drop a rule silently
    out = _render(render, tmp_path)
    _entry(out)
    _local(out, {"node_chek": "hard"})
    r = _gate(out)
    assert r.returncode == 1 and "unknown key `node_chek`" in r.stdout, r.stdout


def test_unknown_nested_config_key_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    _local(out, {"issues": {"requird": True}})
    r = _gate(out)
    assert r.returncode == 1 and "unknown key `issues.requird`" in r.stdout, r.stdout


def test_comment_keys_are_allowed_at_any_level(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    _local(out, {"_comment": "why we deviate", "issues": {"_comment": "x", "required": False}})
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_invalid_local_config_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    (out / LOCAL).write_text("{ nope", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1 and "feature-registry.local.json: invalid JSON" in r.stdout, r.stdout


def test_wrongly_shaped_config_value_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out)
    _local(out, {"layout": "nested"})
    r = _gate(out)
    assert r.returncode == 1 and "`layout` must be one of" in r.stdout, r.stdout
    _local(out, {"issues": None})
    r = _gate(out)
    assert r.returncode == 1 and "`issues` must be an object" in r.stdout, r.stdout
    assert "Traceback" not in r.stderr


# --- v2.92 K1/K2: the keys and the capabilities layout (Kenni's registry) ---

FIX = Path(__file__).parent / "fixtures/kenni-registry"  # two capabilities of Kenni's registry
KREG = "docs/feature-registry"
KENNI = {
    "layout": "capabilities", "root": KREG, "id_pattern": "^{prefix}-US-\\d{3}$",
    "require_registry": True, "story_text_fields": ["title", "as_a", "i_want", "so_that"],
    "story_surfaces": "required", "surfaces": ["web", "ios", "macos", "signal", "cli"],
    "shared_proof_layers": ["backend"], "story_tests": "test_mapping",
    "issues": {"field": "issues", "required": True, "required_for": "covered"},
    "story_status": {"values": ["covered", "partial", "gap", "planned", "deferred"],
                     "deferred": "deferred", "deferred_allows_empty_tests": True},
    "retired_fields": ["blocked_by", "parent", "backlog"], "extra_fields": ["notes"],
}


def _stub_test(out, ref):
    """The file a test ref names, defining each `::` segment (planned refs name none)."""
    if ref.startswith("planned:"):
        return
    base, _, node = ref.partition("::")
    f = out / base
    f.parent.mkdir(parents=True, exist_ok=True)
    have = f.read_text(encoding="utf-8") if f.exists() else ""
    segs = node.split("::") if node else []
    add = "".join(f"def {s}():\n    pass\n" if base.endswith(".py") else f"// {s}\n" for s in segs)
    f.write_text(have + add, encoding="utf-8")


def _kenni(render, tmp_path, *, ids=True, **cfg):
    """Kenni's layout and keys over a copy of two of its capabilities, every test ref
    stubbed; `ids` gives the string items the ids `--assign-ids` would."""
    out = _render(render, tmp_path)
    shutil.copytree(FIX, out / KREG)
    _local(out, {**KENNI, **cfg})
    for p in sorted((out / KREG).glob("*/*.json")):
        if p.name == "_capability.json":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if ids:
            d["acceptance"] = [{"id": f"AC{i}", "text": t} for i, t in enumerate(d["acceptance"], 1)]
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for refs in d["test_mapping"].values():
            for ref in refs:
                _stub_test(out, ref)
    return out


def _edit(out, rel, **over):
    p = out / KREG / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    for key, value in over.items():
        if value is None:
            d.pop(key, None)
        else:
            d[key] = value
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def _green_kenni(render, tmp_path, **cfg):
    out = _kenni(render, tmp_path, **cfg)
    _edit(out, "captures/CAP-US-004.json", test_mapping={"web": []})  # deferred, empty list
    return out


def test_kenni_layout_is_green(render, tmp_path):
    # head field inventory_sections, notes, deferred with an empty list, issue lists
    out = _green_kenni(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_without_project_file_the_template_keys_hold(render, tmp_path):
    # Wächter K1: the defaults are today's template behaviour — a story-less
    # Kenni tree under docs/feature-registry is not even read
    out = _render(render, tmp_path)
    shutil.copytree(FIX, out / KREG)
    _entry(out)
    assert _gate(out).returncode == 0


def test_flat_inventory_with_item_test_lists_and_no_surfaces_stays_green(render, tmp_path):
    # Wächter K1/I2: no surfaces declared — an item's plain `tests` list is its one implicit surface
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"id": "AC1", "text": "Saved.", "tests": ["tests/test_widget.py"]}])
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_required_story_surfaces_empty_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-001.json", surfaces=[])
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001.json: 'surfaces' must be a non-empty list" in r.stdout, r.stdout


def test_required_story_surfaces_unknown_value_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-001.json", surfaces=["web", "android"])
    r = _gate(out)
    assert r.returncode == 1 and "unknown surface(s) ['android']" in r.stdout, r.stdout


def test_missing_story_text_field_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-001.json", so_that=None)
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001.json: missing 'so_that'" in r.stdout, r.stdout


def test_unknown_status_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", status="done")
    r = _gate(out)
    assert r.returncode == 1 and "invalid status 'done'" in r.stdout, r.stdout


def test_missing_status_with_story_status_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", status=None)
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-002.json: missing 'status'" in r.stdout, r.stdout
    assert "retired" not in r.stdout  # with story_status, status is no retired field


def test_issues_not_a_list_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", issues="#116")
    r = _gate(out)
    assert r.returncode == 1 and "'issues' must be a list" in r.stdout, r.stdout


def test_issues_missing_when_required_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", issues=None)
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-002.json: missing 'issues'" in r.stdout, r.stdout


def test_malformed_issue_ref_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", issues=["116"])
    r = _gate(out)
    assert r.returncode == 1 and "malformed issue ref '116'" in r.stdout, r.stdout


def test_empty_test_mapping_list_outside_deferred_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", test_mapping={"ios": []})
    r = _gate(out)
    assert r.returncode == 1 and "'test_mapping.ios' must be a non-empty list" in r.stdout, r.stdout


def test_empty_test_mapping_object_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "captures/CAP-US-004.json", test_mapping={})
    r = _gate(out)
    assert r.returncode == 1 and "'test_mapping' must be a non-empty object" in r.stdout, r.stdout


def test_require_registry_with_missing_root_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, KENNI)
    r = _gate(out)
    assert r.returncode == 1 and "docs/feature-registry does not exist" in r.stdout, r.stdout


def test_json_in_the_root_of_the_capabilities_layout_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    (out / KREG / "documents.json").write_text("{}", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1 and "documents.json: JSON directly in docs/feature-registry" in r.stdout, r.stdout


def test_example_json_in_the_root_stays_allowed(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    (out / KREG / "STORY-0001.example.json").write_text("{}", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_filename_must_match_the_id(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    (out / KREG / "clients/CLI-US-002.json").rename(out / KREG / "clients/CLI-US-009.json")
    r = _gate(out)
    assert r.returncode == 1 and "filename must match story id 'CLI-US-002'" in r.stdout, r.stdout


def test_directory_must_match_the_capability(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/_capability.json", capability="customers")
    r = _gate(out)
    assert r.returncode == 1 and "directory name must match capability 'customers'" in r.stdout, r.stdout


def test_head_without_prefix_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/_capability.json", prefix=None)
    r = _gate(out)
    assert r.returncode == 1 and "clients/_capability.json: 'prefix'" in r.stdout, r.stdout


def test_id_with_a_foreign_prefix_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/_capability.json", prefix="CAP")
    r = _gate(out)
    assert r.returncode == 1 and "'id' must match ^CAP-US-\\d{3}$, got 'CLI-US-001'" in r.stdout, r.stdout


def test_schema_version_2_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/_capability.json", schema_version=2)
    r = _gate(out)
    assert r.returncode == 1 and "schema_version must be 1" in r.stdout, r.stdout


def test_empty_capability_under_require_registry_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    (out / KREG / "empty").mkdir()
    (out / KREG / "empty/_capability.json").write_text(json.dumps(
        {"schema_version": 1, "capability": "empty", "prefix": "EMP"}), encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1 and "docs/feature-registry/empty: a capability without stories" in r.stdout, r.stdout


def test_unknown_test_mapping_key_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-002.json", test_mapping={"android": ["backend/tests/api/v1/test_clients.py"]})
    r = _gate(out)
    assert r.returncode == 1 and "unknown test_mapping key(s) ['android']" in r.stdout, r.stdout


def test_covered_without_issue_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _edit(out, "clients/CLI-US-001.json", issues=[])
    r = _gate(out)
    assert r.returncode == 1 and "status 'covered' needs at least one ref in 'issues'" in r.stdout, r.stdout
