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


# --- T2: Zeitfenster und Sitzungsherkunft über den Phasenwechsel --------------------------

def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _live_repo(render, tmp_path, pattern: str = "{worktree}/t/*.jsonl"):
    """Ein Repository mit einer Fake-Sitzung als Befehl: `start` und `stop` laufen echt."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    fake = tmp_path / "fake-session.sh"
    fake.write_text("#!/bin/sh\nsleep 30\n")
    fake.chmod(0o755)
    data["command"] = f"{fake} --model {{model}} {{prompt}}"
    pol.write_text(json.dumps(data))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": pattern}))
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    return out


def _history(out: Path, issue: int) -> dict:
    return json.loads((out / ".git/process-dispatch/phases" / f"{issue}.json").read_text())


def _phase(d, out: Path, branch: str, issue: int, started: float, *, wt: Path | None = None,
           remote: bool = False, phase: str = "execute") -> None:
    """Ein Phasenstart, wie `start` ihn schreibt (der Record trägt `started`)."""
    rec: dict = {"branch": branch, "issue": issue, "phase": phase, "started": int(started)}
    if wt is not None:
        rec["worktree"] = str(wt)
    if remote:
        rec["remote"] = True
    d._write_record(out, branch, rec)


def _drop_record(out: Path, branch: str) -> None:
    (out / ".git/process-dispatch" / f"{branch}.json").unlink()


def _finish(out: Path):
    import sys
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_transcripts", out / "scripts/process/finish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_issue_sum_survives_the_chains_stop_between_phases(render, tmp_path, monkeypatch):
    """B-1: die Kette stoppt die Plan-Phase (der Record geht) und startet `execute`; das
    Fenster beginnt beim ersten Start und bleibt, beide Phasen zählen, auch nach Stopp und
    manuellem Neu-Dispatch. Eine Nachricht vor dem Fenster zählt nicht."""
    import time
    out = _live_repo(render, tmp_path)
    d = _load_dispatch(out)
    monkeypatch.setattr(d, "disk_refusal", lambda p: None)
    args = dict(issue=7, tier=2, branch="b7", title=None, dry_run=False)
    assert d.start(out, phase="plan", **args) == 0
    try:
        rec = json.loads((out / ".git/process-dispatch/b7.json").read_text())
        wt, since = Path(rec["worktree"]), rec["started"]
        assert _history(out, 7)["branches"]["b7"] == {"windows": [[since, None]], "worktrees": [str(wt)],
                                                      "remote": False}
        _write(wt / "t" / "plan.jsonl", _msg("p1", 10, ts=time.time()), _msg("old", 1000, ts=since - 3600))
        assert d.stop(out, "b7", force=True, keep_report=True) == 0
        time.sleep(1.1)  # the next phase starts on a later second
        assert d.start(out, phase="execute", **args) == 0
        _write(wt / "t" / "execute.jsonl", _msg("e1", 20, ts=time.time()))
        assert d.issue_tokens(out, 7) == (30, 2)
        assert d.stop(out, "b7", force=True) == 0
        assert d.start(out, phase="execute", **args) == 0  # a manual re-dispatch
        history = _history(out, 7)
        assert history["branches"]["b7"]["windows"] == [[since, None]]
        assert history["branches"]["b7"]["worktrees"] == [str(wt)]  # no duplicates
        assert (history["phase"], history["branch"]) == ("execute", "b7")  # today's readers
        assert d.issue_tokens(out, 7) == (30, 2)
    finally:
        d.stop(out, "b7", force=True)


def test_a_history_without_branches_falls_back_to_the_records(render, tmp_path):
    """Wächter: eine Historie von vor v2.92 trägt kein `branches` — die Records gelten,
    ohne Zeitfenster, wie bisher."""
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    _write(wt / "t" / "a.jsonl", _msg("m1", 12, ts=1_000_000))
    (records / "phases").mkdir()
    (records / "phases" / "8.json").write_text(json.dumps({"phase": "plan", "branch": "b8"}))
    _record(records, "b8", issue=8, worktree=str(wt), phase="plan", started=2_000_000_000)
    assert d.issue_tokens(out, 8) == (12, 1)


def test_finish_after_the_review_session_stopped_reports_the_issues_sum(render, tmp_path):
    """#403 AC-3: der Stopp der Review-Sitzung löscht den Record; `finish` misst über die
    Historie, statt `not measured` zu melden."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = time.time() - 1000
    _phase(d, out, "7-widget", 7, t0, wt=wt, phase="execute")
    _phase(d, out, "7-widget", 7, t0 + 100, wt=wt, phase="review")
    _write(wt / "t" / "s.jsonl", _msg("m1", 10, ts=t0 + 10), _msg("m2", 5, ts=t0 + 110))
    _drop_record(out, "7-widget")
    assert _finish(out).usage(out, "7-widget") == (7, "tokens: 15 output over 1 sessions")


def test_a_branch_executed_here_and_reviewed_remotely_keeps_its_local_transcripts(render, tmp_path):
    """Runde 3, M-1: `worktrees` sammelt jede lokale Phase, `remote` bleibt gesetzt."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = time.time() - 1000
    _phase(d, out, "7-widget", 7, t0, wt=wt, phase="execute")
    _phase(d, out, "7-widget", 7, t0 + 100, remote=True, phase="review")
    _phase(d, out, "7-widget", 7, t0 + 200, wt=wt, phase="execute")
    _write(wt / "t" / "s.jsonl", _msg("m1", 10, ts=t0 + 10))
    _drop_record(out, "7-widget")
    assert _history(out, 7)["branches"]["7-widget"] == {"windows": [[int(t0), None]], "worktrees": [str(wt)],
                                                        "remote": True}
    assert _finish(out).usage(out, "7-widget")[1].startswith("tokens: 10 output over 1 sessions")


def test_a_merge_by_finish_closes_the_window_and_a_later_issue_on_the_name_is_not_counted(render, tmp_path):
    """(a) Nach dem Merge über `finish` startet #57 auf demselben Branch-Namen: #42 zählt es nicht."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = time.time() - 1000
    _phase(d, out, "42-x", 42, t0, wt=wt)
    _write(wt / "t" / "a.jsonl", _msg("m1", 10, ts=t0 + 10))
    _finish(out)._done(out, "42-x")
    end = _history(out, 42)["branches"]["42-x"]["windows"][-1][1]
    assert end is not None and end >= t0
    _phase(d, out, "42-x", 57, time.time() + 5, wt=wt)
    _write(wt / "t" / "b.jsonl", _msg("m2", 500, ts=time.time() + 10))
    assert d.issue_tokens(out, 42) == (10, 1)
    assert d.issue_tokens(out, 57) == (500, 1)


def test_a_merge_by_the_train_closes_the_window(render, tmp_path):
    """(b) `forget_branch` (der Zug) schließt das Fenster; (c) ein wiedereröffnetes Issue
    startet erneut auf dem Branch: ein neues Fenster, neue Sitzungen zählen, die Lücke nicht."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = time.time() - 1000
    _phase(d, out, "42-y", 42, t0, wt=wt)
    d.forget_branch(out, "42-y")
    windows = _history(out, 42)["branches"]["42-y"]["windows"]
    assert len(windows) == 1 and windows[0][1] is not None
    closed = windows[0][1]
    _phase(d, out, "42-y", 42, closed + 100, wt=wt)
    assert _history(out, 42)["branches"]["42-y"]["windows"] == [[int(t0), closed], [int(closed) + 100, None]]
    _write(wt / "t" / "a.jsonl", _msg("m1", 1, ts=t0 + 10))
    _write(wt / "t" / "b.jsonl", _msg("m2", 1000, ts=closed + 50))
    _write(wt / "t" / "c.jsonl", _msg("m3", 20, ts=closed + 150))
    assert d.issue_tokens(out, 42)[0] == 21


def test_issues_taking_turns_on_one_branch_each_count_their_own_windows(render, tmp_path):
    """(d) #72 und #73 wechseln sich ab: jede Sitzung zählt zu dem Issue, dessen Fenster
    offen war; der Start des einen schließt das Fenster des anderen (Rückwärts-Index)."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = int(time.time()) - 1000
    _phase(d, out, "shared", 72, t0, wt=wt)
    _phase(d, out, "shared", 73, t0 + 100, wt=wt)
    _phase(d, out, "shared", 72, t0 + 200, wt=wt)
    assert _history(out, 72)["branches"]["shared"]["windows"] == [[t0, t0 + 100], [t0 + 200, None]]
    assert _history(out, 73)["branches"]["shared"]["windows"] == [[t0 + 100, t0 + 200]]
    assert json.loads((records / "phases" / "branches.json").read_text()) == {"shared": [72, 73]}
    _write(wt / "t" / "s1.jsonl", _msg("m1", 1, ts=t0 + 50))
    _write(wt / "t" / "s2.jsonl", _msg("m2", 10, ts=t0 + 150))
    _write(wt / "t" / "s3.jsonl", _msg("m3", 100, ts=t0 + 250))
    assert d.issue_tokens(out, 72) == (101, 2)
    assert d.issue_tokens(out, 73) == (10, 1)


def test_a_message_without_timestamp_counts_and_marks_the_sum_partial(render, tmp_path):
    """Ein Filter über `_epoch` = +inf hätte sie verworfen; sie zählt und macht die Summe unvollständig."""
    import time
    out, records = _setup(render, tmp_path, "{worktree}/t/*.jsonl")
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    t0 = time.time() - 1000
    _phase(d, out, "9-z", 9, t0, wt=wt)
    _write(wt / "t" / "a.jsonl", _msg("m1", 10, ts=t0 + 10), _msg("m2", 3))
    totals, sessions, _covered, _events, unknown = d.issue_token_coverage(out, 9)
    assert totals["output_tokens"] == 13 and sessions == 1 and unknown == 1


def test_an_unreadable_history_still_refuses_start_and_keeps_the_brainstorm_gate(render, tmp_path):
    """Wächter (Runde 4, MAJOR-1): `start` verweigert bei unlesbarer Historie; die
    Brainstorm-Freigabe liest dieselbe Datei, auch mit `branches`."""
    out = _live_repo(render, tmp_path)
    d = _load_dispatch(out)
    history = d._records_dir(out) / "phases" / "42.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("{not json")
    args = dict(issue=42, tier=2, branch="work", title=None, dry_run=True)
    assert d.start(out, phase="plan", **args) == 3
    history.write_text(json.dumps({"phase": "brainstorm", "branch": "work",
                                   "branches": {"work": {"windows": [[1, None]], "worktrees": [], "remote": False}}}))
    assert d.start(out, phase="execute", owner_approved=True, **args) == 3
    assert d.start(out, phase="plan", **args) == 3


def test_a_history_unreadable_after_starts_check_is_rewritten_and_start_succeeds(render, tmp_path, monkeypatch):
    """Ab dem Worker-Start wirft das Mischen nie: eine Historie, die nach der Prüfung in
    `start` unlesbar wurde, gilt als leer und wird neu geschrieben."""
    out = _live_repo(render, tmp_path)
    d = _load_dispatch(out)
    monkeypatch.setattr(d, "disk_refusal", lambda p: None)
    history = d._records_dir(out) / "phases" / "42.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps({"phase": "plan", "branch": "work"}))
    load_policy = d.load_policy

    def corrupting(*a, **k):
        history.write_text("{not json")
        return load_policy(*a, **k)
    monkeypatch.setattr(d, "load_policy", corrupting)
    try:
        assert d.start(out, issue=42, phase="execute", tier=2, branch="work", title=None, dry_run=False) == 0
        got = json.loads(history.read_text())
        assert got["phase"] == "execute" and list(got["branches"]) == ["work"]
    finally:
        d.stop(out, "work", force=True)
