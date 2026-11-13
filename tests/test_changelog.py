"""changelog.py (core, v2.96 A4): one owner of the release-notes entry grammar and of
the marks `[required]`/`[recommended]`/`[optional]` under **What changes.**."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "template/scripts/process"


def _load():
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec = importlib.util.spec_from_file_location("changelog_test", SCRIPTS / "changelog.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


cl = _load()

LOG = """# Changelog

Intro text.

## v2.96.0 — Marks · 2026-11-14

**What changes.**
- [required] Fix the gate that blocks every push.
  More about it.
  - [optional] a nested detail is no item of its own
- [recommended] Better output.
- A point without a mark.

**Effect.**
- Not an item of What changes.

## v2.95.0 — Old

**What changes.**
- Something.

# Archive

**v2.94.0 — Older.** First line.
- Punkt

**v2.93.0 — Oldest.** X.
"""


def test_entries_read_both_forms_with_their_stop_rules():
    found = cl.entries(LOG)
    assert [(v, t) for v, t, _ in found] == [("v2.96.0", "Marks"), ("v2.95.0", "Old"),
                                            ("v2.94.0", "Older"), ("v2.93.0", "Oldest")]
    body = dict((v, b) for v, _, b in found)
    assert "Better output." in body["v2.96.0"] and "Something." not in body["v2.96.0"]
    assert "# Archive" not in body["v2.95.0"] and "Older" not in body["v2.95.0"]  # `# ` stops a heading entry
    assert body["v2.94.0"] == "First line.\n- Punkt" and "X." not in body["v2.94.0"]


def test_notes_keep_the_release_notes_contract():
    assert cl.notes(LOG, "v2.95.0") == ("Old", "**What changes.**\n- Something.\n")
    assert cl.notes(LOG, "v2.94.0") == ("Older", "First line.\n- Punkt\n")
    assert cl.notes(LOG, "v9.9.9") is None
    # a heading alone tells a reader nothing
    assert cl.notes("## v1.3.0 — leer · 2026-10-15\n\n## v1.2.0 — x\n\nX.\n", "v1.3.0") is None


def test_marks_read_the_first_level_items_under_what_changes():
    body = cl.notes(LOG, "v2.96.0")[1]
    assert cl.marks(body) == [("required", "Fix the gate that blocks every push."),
                              ("recommended", "Better output."),
                              (None, "A point without a mark.")]


def test_marks_read_the_german_entry_and_nothing_without_what_changes():
    de = "**Warum.**\n- Grund.\n\n**Was sich ändert.**\n- [optional] Eine neue Option.\n\n**Wirkung.**\n- Mehr.\n"
    assert cl.marks(de) == [("optional", "Eine neue Option.")]
    assert cl.marks("body\n") == []
    assert cl.marks("**Why.**\n- A reason.\n") == []


def test_a_mark_counts_only_as_the_first_thing_after_the_dash():
    body = "**What changes.**\n- **Bold** [required] later.\n- [Required] wrong case.\n- [must] unknown.\n"
    assert [m for m, _ in cl.marks(body)] == [None, None, None]
