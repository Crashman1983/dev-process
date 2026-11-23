"""markdown_read (core, v2.102, #443): one reader of Markdown headings for every gate —
on the text the record readers see, line for line — and one question where that text
and a renderer's could differ (`ambiguity_problem`)."""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "template/scripts/process"


def _load(name: str):
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in the template
    sys.path.insert(0, str(PROC))
    try:
        spec = importlib.util.spec_from_file_location(name, PROC / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(PROC))
        sys.dont_write_bytecode = keep


md = _load("markdown_read")


# --- AC-1: heading() and headings() -------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("##", (2, "")),  # a bare run of `#` is an empty heading
    ("# ", (1, "")),
    ("   ## X", (2, "X")),  # up to three spaces in
    ("    ## X", None),  # four is indented code
    ("## Titel ##", (2, "Titel")),  # a closing run after whitespace is dropped
    ("## Titel ##   ", (2, "Titel")),
    ("### ###", (3, "")),
    ("## C#", (2, "C#")),  # no whitespace before it: part of the text
    ("## foo \\###", (2, "foo \\###")),
    ("####### x", None),  # seven is text
    ("#5 bolt", None),  # no space after the marks
    ("#hashtag", None),
    ("#\tTab", (1, "Tab")),
    ("## x", None),  # a no-break space separates nothing
    ("## Status\n", (2, "Status")),
])
def test_heading_reads_one_line_as_commonmark_atx(line, expected):
    assert md.heading(line) == expected


def test_a_bare_heading_never_joins_the_next_line():
    """#443 AC-2: `##` + `Regel` is an empty heading and a paragraph, not the heading `Regel`."""
    assert md.headings("##\nRegel\n") == [md.Heading(2, "", 1)]
    assert md.heading("##\nRegel") is None  # a line holds no line end


def test_headings_are_the_visible_ones_at_their_own_line():
    text = ("# Title\n\n```\n## In code\n```\n\n<!--\n## In a comment\n-->\n\n"
            "a <!-- note\nstill --> ## not a heading\n\n## Seen ##\n")
    assert md.headings(text) == [md.Heading(1, "Title", 1), md.Heading(2, "Seen", 14)]


def test_an_inline_comment_closed_on_the_line_leaves_the_heading():
    assert md.headings("## A <!-- x --> B\n") == [md.Heading(2, "A  B", 1)]


def test_a_leading_bom_is_dropped():
    assert md.headings("﻿## X\n") == [md.Heading(2, "X", 1)]
    assert md.ambiguity_problem("﻿## X\n") is None


def test_visible_lines_keep_each_piece_at_its_own_line():
    """r2 M2: the rest of a line after `-->` keeps that line's number."""
    assert md.visible_lines("a <!-- x\ny --> b\nc\n") == [(1, "a "), (2, " b"), (3, "c")]
    assert md.visible_lines("<!--\nhidden\n-->\n\n```\ncode\n```\nseen\n") == [(4, ""), (8, "seen")]


def test_comments_blank_keeps_each_line_at_its_own_number():
    """`check_plan_structure._comments_blank` moved here, corrected (r2 M2): v2.101 put
    `a ` on line 2, where the comment closed."""
    assert md._comments_blank("a <!-- x\ny --> b\nc") == "a \n b\nc"


# --- AC-2: ambiguity_problem ----------------------------------------------------------

CASES = {
    "suffix closer": ("```md\n```suffix\n## Regel\n```\n", "line 3 reads as text, but as quoted"),
    "fence in a comment": ("<!--\n```\n-->\n\n## Regel\n",
                           "line 2: a code fence stands inside the HTML comment opened on line 1"),
    "line separator": ("## Regel ## Zwei\n", "line 1 holds a line separator (U+2028)"),
    "comment across a heading": ("a <!-- c\n## H\n--> b\n",
                                 "line 2: an HTML comment opened on line 1 closes on line 3"),
    "unclosed comment": ("x\n\n<!--\n## H\n", "line 3: an HTML comment opens here and never closes"),
    "indented fence": ("text\n    ```\n## H\n", "line 2: a code fence opens 4 columns in"),
    "empty comment": ("<!-->\n## H\n", "line 1: `<!-->` closes a comment for a renderer"),
}


@pytest.mark.parametrize("name", CASES)
def test_ambiguity_problem_names_the_line_and_the_remedy(name):
    text, needle = CASES[name]
    problem = md.ambiguity_problem(text)
    assert problem is not None and needle in problem, problem
    assert ";" in problem  # what to do follows the finding


def test_each_rule_has_its_own_message():
    messages = {md.ambiguity_problem(text).split(" — ")[0].split(":", 1)[-1].strip()
                for text, _ in CASES.values()}
    assert len(messages) == len(CASES), messages


@pytest.mark.parametrize("char", [" ", "\x85", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"])
def test_every_odd_line_end_is_reported(char):
    assert f"U+{ord(char):04X}" in md.ambiguity_problem(f"# T\n\n## A{char}B\n")


def test_a_heading_with_an_unclosed_inline_comment_is_reported_on_its_line():
    assert md.ambiguity_problem("## A <!-- c\n-->\n").startswith("line 1:")


@pytest.mark.parametrize("text", [
    "# Doc\n\n## A\n\ntext <!-- note --> more\n\n```\n<!--\n```\n\n## B\n",  # `<!--` in code
    "- item\n\n    ```\n    code\n    ```\n\n## After\n",  # an aligned fence in a list
    "1. step\n\n   ```bash\n   run\n   ```\n",
    "<!--\nmulti\nline\n-->\n\n## H\n",
    "a <!-- spans\ntwo lines --> b\n\n## H\n",
    "text\n\n    indented code\n\n## H\n",
    "write `<!--` to start a comment\n\n```\nx\n```\n",
])
def test_an_unambiguous_document_has_no_problem(text):
    assert md.ambiguity_problem(text) is None


def test_the_first_line_wins():
    assert md.ambiguity_problem("a <!-- c\n## H\n--> b\n\n## A B\n").startswith("line 2:")


# --- one owner: the moved names, re-exported --------------------------------------

MOVED = ("_legacy_scan", "_strict_scan", "fenced_lines", "fence_drift_problem", "uncommented",
         "_inline_uncommented", "_closing_run", "_BLOCK_COMMENT", "_ASCII_PUNCT")


def test_the_readers_moved_here_and_stay_importable_from_the_gates():
    names = ("markdown_read", "check_review", "check_plan_structure", "attest_evidence",
             "process_git", "registry_config")
    saved = {n: sys.modules.pop(n, None) for n in names}
    sys.path.insert(0, str(PROC))
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        import check_plan_structure
        import check_review
        import markdown_read
        for name in MOVED:
            assert getattr(check_review, name) is getattr(markdown_read, name), name
            assert name not in _defined(PROC / "check_review.py"), name
        assert check_plan_structure._comments_blank is markdown_read._comments_blank
        assert "_comments_blank" not in _defined(PROC / "check_plan_structure.py")
        assert "_quoted_blank" in _defined(PROC / "check_plan_structure.py")  # fence-only, stays
    finally:
        sys.dont_write_bytecode = keep
        sys.path.remove(str(PROC))
        for n, mod in saved.items():
            sys.modules.pop(n, None)
            if mod is not None:
                sys.modules[n] = mod


def _defined(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return out


def test_the_owner_imports_no_gate():
    """r1 M4: stdlib only — `check_overlays` loads it beside itself, without `check_review`."""
    tree = ast.parse((PROC / "markdown_read.py").read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= {"__future__", "bisect", "re", "typing"}, imported


def test_record_readers_read_as_before():
    """#250: the record readers' reading is unchanged by the move."""
    text = "a <!-- x\ny --> b\n```\nREVIEW work=1\n```\n<!--\nhidden\n-->\nc\n"
    assert md.uncommented(md.fenced_lines(text)[0][0][1]) == "a <!-- x"
    joined = "\n".join(line for _n, line in md.fenced_lines(text)[0])
    assert md.uncommented(joined) == "a  b\nc"


def test_heading_rule_reads_a_file_and_a_line():
    rule = md.HeadingRule(r"Decisions\b", range(2, 5), flags=__import__("re").IGNORECASE)
    assert rule.search("x\n### decisions\n") and rule.match("   ## Decisions ##") == (2, "Decisions")
    assert not rule.search("# Decisions\n") and not rule.search("<!--\n## Decisions\n-->\n")
    assert not rule.search("```\n## Decisions\n```\n") and not rule.search("##\nDecisions\n")
