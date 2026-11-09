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


def _gate(out, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_feature_registry.py"), ".", *args],
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
    # v2.92 D1: the registry holds proven behaviour and addressable targets; the
    # work log stays in GitHub
    assert "Proven behaviour and addressable targets — not a work log" in doc
    assert "GitHub" in doc and '"state": "target"' in doc
    # #404 AC-10: the writing rule and the split rule
    assert "## Writing rule and split rule" in doc
    assert "One behaviour per item, in the present tense" in doc and "Split rule" in doc
    for section in ("## Configuration", "## Overlay: the project's choices", "## Migration"):
        assert section in doc, section
    assert "docs/process/feature-registry.local.json" in doc and "--assign-ids --write" in doc
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
    "test_ref_roots": ["backend/", "frontend-react/", "ios/"], "planned_refs": True,
    "node_check": "hard",
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


def test_kenni_planned_placeholder_and_nodes_are_green(render, tmp_path):
    # K4 on Kenni's own refs: stack roots, `::node` per segment (hard), planned:#n:<text>
    out = _kenni(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    ref = "backend/tests/api/v1/test_clients.py::test_gone"
    _edit(out, "clients/CLI-US-002.json", test_mapping={"backend": [ref]})
    r = _gate(out)
    assert r.returncode == 1 and "node 'test_gone' not defined" in r.stdout, r.stdout


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


def test_default_issue_field_pr_link_is_a_note_not_a_failure(render, tmp_path):
    """Wächter: Das Template-Feld `issue` ist ein Herkunftsverweis — Issue oder PR (Modul-Doku);
    ein PR-Link oder anderes Format ist ein Hinweis, kein Fehler wie vor v2.92."""
    out = _render(render, tmp_path)
    _entry(out, issue="https://github.com/o/r/pull/12")
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "malformed issue ref" in r.stdout and "note" in r.stdout, r.stdout


def test_default_issue_null_or_non_string_is_no_failure(render, tmp_path):
    """Wächter (v2.92 Refute): `issue: null` gilt als nicht gesetzt, ein anderer Typ ist ein Hinweis."""
    out = _render(render, tmp_path)
    _entry(out, issue=None)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    _entry(out, issue=412)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "'issue' should be a string" in r.stdout, r.stdout


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


# --- v2.92 K4: test refs ---

def test_dead_node_is_a_note_by_default(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, tests=["tests/test_widget.py::test_gone"])
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "node 'test_gone' not defined in tests/test_widget.py" in r.stdout, r.stdout


def test_dead_node_is_hard_with_node_check_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"node_check": "hard"})
    _entry(out, tests=["tests/test_widget.py::test_gone"])
    r = _gate(out)
    assert r.returncode == 1 and "node 'test_gone' not defined" in r.stdout, r.stdout
    _entry(out, tests=["tests/test_widget.py::test_widget"])
    assert _gate(out).returncode == 0


def test_every_node_segment_is_checked(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"node_check": "hard"})
    _entry(out, tests=["tests/test_widget.py::TestBox::test_widget::test_lid"])
    (out / "tests/test_widget.py").write_text("class TestBox:\n    def test_widget(self): pass\n")
    r = _gate(out)
    assert r.returncode == 1 and "node 'test_lid'" in r.stdout and "'TestBox'" not in r.stdout, r.stdout


def test_node_in_a_non_python_file_is_a_substring(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"node_check": "hard"})
    (out / "web").mkdir()
    (out / "web/box.spec.ts").write_text("test('opens the box', () => {});\n")
    _entry(out, tests=["web/box.spec.ts::opens the box"])
    assert _gate(out).returncode == 0
    _entry(out, tests=["web/box.spec.ts::closes the box"])
    r = _gate(out)
    assert r.returncode == 1 and "node 'closes the box' not found in web/box.spec.ts" in r.stdout, r.stdout


def test_unparsable_python_follows_node_check(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, tests=["tests/test_widget.py::test_widget"])
    (out / "tests/test_widget.py").write_text("def test_widget(:\n")
    r = _gate(out)
    assert r.returncode == 0 and "cannot parse tests/test_widget.py" in r.stdout, r.stdout
    _local(out, {"node_check": "hard"})
    r = _gate(out)
    assert r.returncode == 1 and "cannot parse tests/test_widget.py" in r.stdout, r.stdout


def test_ref_outside_the_test_ref_roots_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"test_ref_roots": ["backend/"]})
    _entry(out)
    r = _gate(out)
    assert r.returncode == 1 and "must start with one of ['backend/']" in r.stdout, r.stdout


def test_planned_ref_only_with_planned_refs(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, tests=["tests/test_widget.py", "planned:#12:x"])
    r = _gate(out)
    assert r.returncode == 1 and "planned:#12:x" in r.stdout and "planned_refs" in r.stdout, r.stdout
    _local(out, {"planned_refs": True})
    assert _gate(out).returncode == 0
    _entry(out, tests=["tests/test_widget.py", "planned:12:x"])
    r = _gate(out)
    assert r.returncode == 1 and "malformed placeholder" in r.stdout, r.stdout


def test_a_planned_ref_is_never_proof(render, tmp_path):
    # an entry whose only test is a placeholder proves nothing
    out = _render(render, tmp_path)
    _local(out, {"planned_refs": True})
    _entry(out, tests=["planned:#12:the widget test"])
    r = _gate(out)
    assert r.returncode == 1 and "no existing test" in r.stdout, r.stdout


# --- v2.92 I1: item ids (#404 AC-1, AC-14) ---

def test_item_without_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"text": "Saved widgets survive a restart."}])
    r = _gate(out)
    assert r.returncode == 1 and "acceptance[0] has no 'id'" in r.stdout and "--assign-ids" in r.stdout, r.stdout


def test_string_item_is_hard(render, tmp_path):
    # Kenni's items today: plain strings, references by position
    out = _kenni(render, tmp_path, ids=False)
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001.json: acceptance[0] has no 'id'" in r.stdout, r.stdout


def test_duplicate_item_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"id": "AC1", "text": "a"}, {"id": "AC1", "text": "b"}])
    r = _gate(out)
    assert r.returncode == 1 and "STORY-0002#AC1 is used twice" in r.stdout, r.stdout


def test_lower_case_item_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"id": "ac1", "text": "a"}])
    r = _gate(out)
    assert r.returncode == 1 and "acceptance[0] 'id' must match ^AC[1-9]\\d*$, got 'ac1'" in r.stdout, r.stdout


# --- v2.92 I2: item fields (#404 AC-2, AC-3, AC-3a, AC-15, AC-22) ---

def _item(out, rel, **fields):
    """CLI-US-001's (web, ios, macos) first item, with `fields` set on it."""
    p = out / KREG / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    d["acceptance"][0].update(fields)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


BACKEND_TEST = "backend/tests/api/v1/test_clients.py"
WEB_TEST = "frontend-react/src/api/engagements.test.ts"


def test_item_fields_on_kenni_are_green(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", surfaces=["web", "ios"], state={"web": "proven", "ios": "target"},
          issue="#874", tests={"web": [WEB_TEST]}, design="anchor reserved for #404 B")
    _item(out, "clients/CLI-US-002.json", owned_by="backend", tests={"backend": [BACKEND_TEST]})
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_report_states_the_owned_by_share_per_capability(render, tmp_path):
    # #404 AC-22: client items drifting into "owned_by" show up in the number
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-002.json", owned_by="backend", tests={"backend": [BACKEND_TEST]})
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "items owned_by a shared proof layer, per capability: captures 0/40, clients 1/21" in r.stdout, r.stdout


def test_item_surfaces_outside_the_story_are_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-002.json", surfaces=["web"])  # the story is ios, macos
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-002#AC1: surfaces ['web'] outside" in r.stdout, r.stdout


def test_state_key_outside_the_item_surfaces_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", surfaces=["web"], state={"ios": "proven"})
    r = _gate(out)
    assert r.returncode == 1 and "state key(s) ['ios'] outside the item's surfaces" in r.stdout, r.stdout


def test_unknown_state_value_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", state="done")
    r = _gate(out)
    assert r.returncode == 1 and "state must be 'proven' or 'target'" in r.stdout, r.stdout


def test_target_without_issue_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", state={"web": "target"})
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001#AC1: state 'target' needs an 'issue'" in r.stdout, r.stdout


def test_tests_list_on_two_surfaces_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", surfaces=["web", "ios"], tests=[WEB_TEST])
    r = _gate(out)
    assert r.returncode == 1 and "a plain 'tests' list fits an item with exactly one surface" in r.stdout, r.stdout


def test_tests_list_on_one_surface_is_green(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", surfaces=["web"], tests=[WEB_TEST])
    assert _gate(out).returncode == 0


def test_tests_key_for_a_surface_the_item_lacks_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", surfaces=["web"], tests={"ios": [WEB_TEST]})
    r = _gate(out)
    assert r.returncode == 1 and "tests key 'ios' is neither one of the item's surfaces" in r.stdout, r.stdout


def test_shared_layer_tests_without_owned_by_are_hard(render, tmp_path):
    # a backend test must not stand in for client behaviour (AC-22)
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", tests={"backend": [BACKEND_TEST]})
    r = _gate(out)
    assert r.returncode == 1 and "tests key 'backend' is a shared proof layer" in r.stdout, r.stdout


def test_owned_by_outside_the_shared_layers_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", owned_by="server")
    r = _gate(out)
    assert r.returncode == 1 and "owned_by 'server' is not one of shared_proof_layers" in r.stdout, r.stdout


def test_dead_item_test_path_is_hard(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    _item(out, "clients/CLI-US-001.json", tests={"web": ["frontend-react/gone.test.ts"]})
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001#AC1: tests.web: test path does not exist" in r.stdout, r.stdout


def test_item_surfaces_without_project_surfaces_are_a_note(render, tmp_path):
    # AC-3: no declared surfaces — a note asking to declare them, no subset check
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"id": "AC1", "text": "a", "surfaces": ["web"], "state": "proven",
                             "tests": ["tests/test_widget.py"]}])
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "STORY-0002#AC1: item 'surfaces' without project surfaces — declare `surfaces`" in r.stdout, r.stdout


def test_implicit_surface_rejects_a_state_map(render, tmp_path):
    # AC-3a: one implicit surface takes a single state value, not a map
    out = _render(render, tmp_path)
    _entry(out, acceptance=[{"id": "AC1", "text": "a", "state": {"web": "proven"}}])
    r = _gate(out)
    assert r.returncode == 1 and "state key(s) ['web'] outside the item's surfaces" in r.stdout, r.stdout


def test_story_without_surfaces_falls_back_to_the_project_surfaces(render, tmp_path):
    out = _render(render, tmp_path)
    _local(out, {"surfaces": ["web", "ios"], "story_surfaces": "optional"})
    _entry(out, acceptance=[{"id": "AC1", "text": "a", "surfaces": ["ios"], "tests": ["tests/test_widget.py"]}])
    assert _gate(out).returncode == 0
    _entry(out, acceptance=[{"id": "AC1", "text": "a", "surfaces": ["cli"]}])
    r = _gate(out)
    assert r.returncode == 1 and "surfaces ['cli'] outside" in r.stdout, r.stdout


def test_strict_item_tests_off_is_one_note_per_capability(render, tmp_path):
    out = _green_kenni(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    notes = [line for line in r.stdout.splitlines() if "acceptance item(s) without an existing test" in line]
    assert len(notes) == 2 and any("docs/feature-registry/clients: 21 " in n for n in notes), notes


def test_strict_item_tests_on_fails_an_item_without_tests(render, tmp_path):
    out = _green_kenni(render, tmp_path, strict_item_tests=True)
    r = _gate(out)
    assert r.returncode == 1 and "CLI-US-001#AC1: no existing test (strict_item_tests)" in r.stdout, r.stdout


# --- v2.92 M1: --assign-ids [--write] ---

def _raw_entry(out, text, name="STORY-0002.json"):
    d = out / REG
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    return d / name


def _acceptance(path):
    return json.loads(path.read_text(encoding="utf-8"))["acceptance"]


def test_assign_ids_numbers_strings_by_position(render, tmp_path):
    out = _render(render, tmp_path)
    p = _raw_entry(out, json.dumps({"id": "STORY-0002", "acceptance": ["a", "b", {"text": "c"}]}, indent=2))
    r = _gate(out, "--assign-ids", "--write")
    assert r.returncode == 0, r.stdout
    assert _acceptance(p) == [{"id": "AC1", "text": "a"}, {"id": "AC2", "text": "b"},
                              {"id": "AC3", "text": "c"}]


def test_assign_ids_collision_takes_the_maximum_plus_one(render, tmp_path):
    # AC2 is taken by an existing item, AC3 then by this run's own assignment
    out = _render(render, tmp_path)
    p = _raw_entry(out, json.dumps({"id": "STORY-0002", "acceptance": [
        "a", "b", {"id": "AC2", "text": "c"}, "d"]}, indent=2))
    r = _gate(out, "--assign-ids", "--write")
    assert r.returncode == 0, r.stdout
    assert [i["id"] for i in _acceptance(p)] == ["AC1", "AC3", "AC2", "AC4"]
    p = _raw_entry(out, json.dumps({"id": "STORY-0002", "acceptance": [
        {"id": "AC2", "text": "a"}, "b", "c"]}, indent=2))
    assert _gate(out, "--assign-ids", "--write").returncode == 0
    assert [i["id"] for i in _acceptance(p)] == ["AC2", "AC3", "AC4"]


def test_assign_ids_reports_a_nonconforming_id(render, tmp_path):
    out = _render(render, tmp_path)
    p = _raw_entry(out, json.dumps({"id": "STORY-0002", "acceptance": [{"id": "AC-1", "text": "a"}, "b"]}))
    r = _gate(out, "--assign-ids", "--write")
    assert r.returncode == 1 and "STORY-0002: item id 'AC-1' does not match" in r.stdout, r.stdout
    assert [i["id"] for i in _acceptance(p)] == ["AC-1", "AC2"]  # reported, never rewritten


def test_assign_ids_without_write_changes_nothing(render, tmp_path):
    out = _render(render, tmp_path)
    text = json.dumps({"id": "STORY-0002", "acceptance": ["a"]}, indent=2) + "\n"
    p = _raw_entry(out, text)
    r = _gate(out, "--assign-ids")
    assert r.returncode == 0 and "would assign 1 item id(s)" in r.stdout and "--write" in r.stdout, r.stdout
    assert p.read_text(encoding="utf-8") == text


def test_assign_ids_twice_changes_nothing_the_second_time(render, tmp_path):
    out = _render(render, tmp_path)
    p = _raw_entry(out, json.dumps({"id": "STORY-0002", "acceptance": ["a", "b"]}, indent=4))
    assert _gate(out, "--assign-ids", "--write").returncode == 0
    once = p.read_text(encoding="utf-8")
    r = _gate(out, "--assign-ids", "--write")
    assert r.returncode == 0 and "nothing to assign" in r.stdout, r.stdout
    assert p.read_text(encoding="utf-8") == once


def test_assign_ids_keeps_indent_and_umlauts(render, tmp_path):
    out = _render(render, tmp_path)
    p = _raw_entry(out, '{\n    "id": "STORY-0002",\n    "acceptance": [\n        "Größe ändert sich"\n    ]\n}')
    assert _gate(out, "--assign-ids", "--write").returncode == 0
    assert p.read_text(encoding="utf-8") == (
        '{\n    "id": "STORY-0002",\n    "acceptance": [\n        {\n'
        '            "id": "AC1",\n            "text": "Größe ändert sich"\n        }\n    ]\n}\n')


def test_assign_ids_migrates_the_kenni_layout(render, tmp_path):
    out = _kenni(render, tmp_path, ids=False)
    _edit(out, "captures/CAP-US-004.json", test_mapping={"web": []})
    assert _gate(out).returncode == 1  # string items carry no id yet
    r = _gate(out, "--assign-ids", "--write")
    assert r.returncode == 0 and "docs/feature-registry/clients/CLI-US-002.json: assigned 13 item id(s)" \
        in r.stdout, r.stdout
    items = _acceptance(out / KREG / "clients/CLI-US-002.json")
    assert [i["id"] for i in items] == [f"AC{n}" for n in range(1, 14)]
    assert _gate(out).returncode == 0
    head = (out / KREG / "clients/_capability.json").read_text(encoding="utf-8")
    assert '"prefix": "CLI"' in head  # heads are no stories: untouched
