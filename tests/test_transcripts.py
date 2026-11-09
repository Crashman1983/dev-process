"""#403: Claude Codes Transkripte je Worktree finden (`{worktree_slug}`), die Summe eines
Issues über Phasenwechsel halten und den Grund einer fehlenden Messung benennen."""
import datetime as dt
import importlib.util
import json
import os
import subprocess
from pathlib import Path


def _load_dispatch(out: Path):
    spec = importlib.util.spec_from_file_location("dispatch_transcripts", out / "scripts/process/dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _msg(mid: str, out_tokens: int, *, cwd: str | None = None, model: str = "claude-big-1",
         ts: float | None = None) -> str:
    line: dict = {"type": "assistant", "message": {"id": mid, "model": model,
                                                    "usage": {"input_tokens": 1, "output_tokens": out_tokens}},
                  "requestId": f"r-{mid}"}
    if cwd is not None:
        line["cwd"] = cwd
    if ts is not None:
        line["timestamp"] = _iso(ts)
    return json.dumps(line) + "\n"


def _write(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def _setup(render, tmp_path, pattern: str | None):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    if pattern is not None:
        (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": pattern}))
    records = out / ".git/process-dispatch"
    records.mkdir(parents=True, exist_ok=True)
    return out, records


def _record(records: Path, branch: str, **rec) -> None:
    (records / f"{branch}.json").write_text(json.dumps({"branch": branch, **rec}))


# --- T1: {worktree_slug} -----------------------------------------------------------------

def test_worktree_slug_is_claude_codes_project_directory_name(render, tmp_path):
    """AC-1: jedes Zeichen außer [A-Za-z0-9] wird `-` (Claude Code, `k(e)`), nicht nur `/`."""
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    assert d.worktree_slug("/home/x/.claude/worktrees/a_b") == "-home-x--claude-worktrees-a-b"
    assert d.worktree_slug("/home/user") == "-home-user"


def test_worktrees_sharing_a_slug_count_only_their_own_sessions(render, tmp_path):
    """`a.b` und `a_b` landen im selben Projektverzeichnis: je Sitzungsdatei entscheidet
    ihr `cwd`, ein Subagent folgt seiner Sitzung (er trägt ein eigenes `cwd`)."""
    proj = tmp_path / "projects"
    out, records = _setup(render, tmp_path, str(proj) + "/{worktree_slug}/**/*.jsonl")
    d = _load_dispatch(out)
    dot, under = tmp_path / "w" / "a.b", tmp_path / "w" / "a_b"
    slug = d.worktree_slug(str(dot))
    assert slug == d.worktree_slug(str(under))
    _write(proj / slug / "s1.jsonl", _msg("m1", 10, cwd=str(dot)))
    _write(proj / slug / "s1" / "subagents" / "agent-1.jsonl", _msg("m2", 5, cwd=str(dot / "sub")))
    _write(proj / slug / "s2.jsonl", _msg("m3", 100, cwd=str(under)))
    _write(proj / slug / "s2" / "subagents" / "agent-2.jsonl", _msg("m4", 50, cwd="/elsewhere"))
    _record(records, "1-dot", issue=1, worktree=str(dot), phase="plan")
    _record(records, "2-under", issue=2, worktree=str(under), phase="plan")
    assert d.issue_tokens(out, 1) == (15, 1)
    assert d.issue_tokens(out, 2) == (150, 1)


def test_a_worktree_under_a_symlink_finds_its_transcripts_through_realpath(render, tmp_path):
    """Claude Code bildet den Slug aus `realpath(cwd)` (macOS: /tmp → /private/tmp)."""
    proj = tmp_path / "projects"
    out, records = _setup(render, tmp_path, str(proj) + "/{worktree_slug}/*.jsonl")
    d = _load_dispatch(out)
    real = tmp_path / "real" / "wt"
    real.mkdir(parents=True)
    (tmp_path / "link").symlink_to(tmp_path / "real")
    linked = tmp_path / "link" / "wt"
    _write(proj / d.worktree_slug(os.path.realpath(linked)) / "s.jsonl", _msg("m1", 7, cwd=os.path.realpath(linked)))
    _record(records, "3-link", issue=3, worktree=str(linked), phase="plan")
    assert d.issue_tokens(out, 3) == (7, 1)


def test_a_slug_over_200_characters_globs_its_hash_and_checks_cwd(render, tmp_path):
    """Über 200 Zeichen hängt Claude Code einen Hash an: der Glob nimmt `-*`, und nur das
    Verzeichnis, dessen Sitzung `cwd` = Worktree trägt, zählt (gleiches Präfix, anderer Pfad)."""
    proj = tmp_path / "projects"
    out, records = _setup(render, tmp_path, str(proj) + "/{worktree_slug}/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / ("x" * 230)
    other = tmp_path / ("x" * 230 + "y")
    slug = d.worktree_slug(str(wt))
    assert len(slug) > 200 and d.worktree_slug(str(other))[:200] == slug[:200]
    _write(proj / (slug[:200] + "-1a2b3c") / "s.jsonl", _msg("m1", 3, cwd=str(wt)))
    _write(proj / (slug[:200] + "-9z8y7x") / "s.jsonl", _msg("m2", 900, cwd=str(other)))
    _record(records, "4-long", issue=4, worktree=str(wt), phase="plan")
    assert d.issue_tokens(out, 4) == (3, 1)


def test_a_subagent_transcript_counts_and_is_no_session_of_its_own(render, tmp_path):
    """`**` mit `recursive=True` findet `<session>/subagents/*.jsonl`; `sessions` zählt
    nur Sitzungsdateien auf oberster Ebene."""
    proj = tmp_path / "projects"
    out, records = _setup(render, tmp_path, str(proj) + "/{worktree_slug}/**/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    slug = d.worktree_slug(str(wt))
    _write(proj / slug / "s.jsonl", _msg("m1", 10, cwd=str(wt)))
    _write(proj / slug / "s" / "subagents" / "agent-a.jsonl", _msg("m2", 4, cwd=str(wt), model="claude-small-1"))
    _record(records, "5-sub", issue=5, worktree=str(wt), phase="plan")
    assert d.issue_tokens(out, 5) == (14, 1)


def test_a_subagents_usage_in_its_parents_tool_result_counts_once_under_its_model(render, tmp_path):
    """Das Agent-Werkzeug legt die Usage des Subagenten in `toolUseResult` ab; sie steht
    schon in `subagents/*.jsonl` und zählt dort, unter dem Modell des Subagenten."""
    proj = tmp_path / "projects"
    out, records = _setup(render, tmp_path, str(proj) + "/{worktree_slug}/**/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    slug = d.worktree_slug(str(wt))
    parent = json.dumps({"type": "user", "cwd": str(wt),
                         "toolUseResult": {"status": "completed", "totalTokens": 75,
                                           "usage": {"input_tokens": 5, "output_tokens": 70}}}) + "\n"
    _write(proj / slug / "s.jsonl", _msg("m1", 10, cwd=str(wt)), parent)
    _write(proj / slug / "s" / "subagents" / "agent-a.jsonl", _msg("m2", 70, cwd=str(wt), model="claude-small-1"))
    _record(records, "6-agent", issue=6, worktree=str(wt), phase="plan")
    assert d.issue_tokens(out, 6) == (80, 1)
    by_model, _unknown = d.model_token_usage(out)
    assert by_model["claude-small-1"]["output_tokens"] == 70
    assert d.UNKNOWN_MODEL not in by_model


def test_worktree_placeholder_keeps_its_meaning(render, tmp_path):
    """Wächter, AC-2: `{worktree}` ist der Pfad selbst; ohne `{worktree_slug}` prüft
    niemand ein `cwd`, das andere Harnesses nicht schreiben."""
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt [7]"
    _write(wt / "t" / "a.jsonl", '{"output_tokens": 9}\n')
    _record(records, "7-x", issue=7, worktree=str(wt), phase="plan")
    assert d.issue_tokens(out, 7) == (9, 1)
