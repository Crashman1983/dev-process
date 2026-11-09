"""feature-inventory gate (lean pass): capability -> acceptance -> proving
tests; the work-log axis (status, blocked_by, parent) moved to GitHub."""
import json
import subprocess
import sys

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
