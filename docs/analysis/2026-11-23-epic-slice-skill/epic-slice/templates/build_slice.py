#!/usr/bin/env python3
"""Vorlage: eine Scheibe parallel bauen, je Issue prüfen, lokal zusammenführen.

    python build_slice.py <epic-blatt.md> <scheiben-id> <workers.json> [<run-dir>]

Eine Vorlage, kein fester Ablauf: Der steuernde Agent kopiert sie und ändert
sie für die Aufgabe (weitere Stufen, eine zweite Korrekturrunde, andere
Rollen). Liegt die Kopie nicht mehr im Skill-Ordner, zeigt ``EPIC_SLICE_HOME``
auf ihn. Am Ende stehen ein zusammengeführter lokaler Zweig und
``slice-report.json`` für den Integrationsowner. Landen auf main ist nicht
Teil davon.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("EPIC_SLICE_HOME") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(HOME / "scripts"))
from flow import Flow, default_run_dir, load_sheet

BUILD = """Du baust Issue #{issue} ({title}) als Teil des Epics {epic}.

Referenz: {ref_build}. Prüfe zuerst, dass du sie hast: {ref_check}
Stimmt die Referenz nicht, hör auf und melde das in "open_points".

Dir gehören nur diese Dateien: {owns}
Gemeinsame Dateien ({shared}) änderst du nicht. Brauchst du dort etwas,
beschreibe es in "shared_requests" (je Eintrag ein Objekt mit file, change, reason).
Querschnittsverhalten mit festem Owner, das du nicht änderst: {cross}

Akzeptanzkriterien stehen im Issue #{issue}. Schreibe je Kriterium einen Test,
führe diese Tests aus: {tests}
Committe alles in deinem Arbeitsverzeichnis mit der Issue-Nummer im Betreff.
Nicht committete Arbeit zählt nicht.

Ergebnis: summary, tests_run (Befehl und Ausgang), shared_requests (Liste),
open_points (Liste; leer, wenn nichts offen ist)."""

REPAIR = """Dein Zweig für Issue #{issue} ist so nicht übernehmbar: {problem}
Nimm Änderungen an Dateien zurück, die dir nicht gehören; was du dort brauchst,
gehört in "shared_requests". Committe alles. Ergebnis: summary, shared_requests, open_points."""

CHECK = """Prüfe den Stand in diesem Arbeitsverzeichnis gegen Issue #{issue} ({title}).
Du hast ihn nicht gebaut. Lies das Issue und den Diff gegen {base}.
Nenne nur, was ein Kriterium verfehlt oder kaputt ist; Stilfragen nicht.
Führe aus: {tests}
Ergebnis: verdict ("ok" oder "findings"), findings (Liste aus Datei, Zeile, Befund)."""

BUILT = {"summary": "str", "tests_run": "any", "shared_requests": "list", "open_points": "list"}
REPAIRED = {"summary": "str", "shared_requests": "list", "open_points": "list"}


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    sheet = load_sheet(sys.argv[1])
    sl = next((s for s in sheet["slices"] if str(s["id"]) == sys.argv[2]), None)
    if sl is None:
        print(f"Scheibe {sys.argv[2]} steht nicht im Blatt")
        return 2
    slug = f"{sheet['epic']}-{sl['id']}"
    run_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else default_run_dir(".", slug)
    flow = Flow(".", run_dir, sys.argv[3], max_parallel=sl.get("max_parallel", 4))
    shared = sheet.get("shared_paths", [])
    cross = "; ".join(f"{c['behavior']} → {c['owner']}" for c in sheet.get("cross_cutting", []))
    bootstrap = sheet.get("bootstrap", [])
    base = sl["base"]
    if "/" in base:
        remote = base.split("/", 1)[0]
        if remote in flow.git("remote").stdout.split():
            flow.git("fetch", remote)
    base_sha = flow.git("rev-parse", "--verify", f"{base}^{{commit}}").stdout.strip()
    if not base_sha:
        print(f"Basis {base} gibt es nicht")
        return 2
    flow.log(f"Scheibe {slug} ab {base} ({base_sha[:10]})")

    def fields(issue: dict) -> dict:
        return {
            "issue": issue["issue"],
            "title": issue.get("title", ""),
            "epic": sheet["epic"],
            "ref_build": sheet["reference"]["build"],
            "ref_check": sheet["reference"]["check"],
            "owns": ", ".join(issue["owns"]),
            "shared": ", ".join(shared) or "keine",
            "cross": cross or "keines",
            "tests": " && ".join(issue.get("tests", [])) or "die Tests, die du schreibst",
            "base": base,
        }

    def problems(path: Path, branch: str, issue: dict) -> list[str]:
        found = flow.unfinished(path, base_sha)
        outside = flow.ownership(branch, base_sha, issue["owns"], shared)
        touched = outside["foreign"] + outside["shared"]
        if touched:
            found.append("fremde oder gemeinsame Dateien geändert: " + ", ".join(touched))
        return found

    def build(_prev: dict, issue: dict, _i: int) -> dict | None:
        num = issue["issue"]
        path, branch = flow.worktree(f"issue-{num}", base_sha, bootstrap=bootstrap)
        result = flow.agent(
            BUILD.format(**fields(issue)),
            label=f"build-{num}",
            role="build",
            cwd=path,
            required=BUILT,
            state=base_sha,
        )
        return result and {"issue": num, "path": path, "branch": branch, "build": result}

    def own(prev: dict, issue: dict, _i: int) -> dict | None:
        num = issue["issue"]
        found = problems(prev["path"], prev["branch"], issue)
        if found:
            flow.agent(
                REPAIR.format(issue=num, problem="; ".join(found)),
                label=f"repair-{num}",
                role="build",
                cwd=prev["path"],
                required=REPAIRED,
                state=flow.head(prev["path"]),
            )
            found = problems(prev["path"], prev["branch"], issue)
            if found:
                flow.log(f"#{num}: nicht übernommen — {'; '.join(found)}")
                return None
        repaired = flow.recall(f"repair-{num}") or {}
        prev["shared_requests"] = prev["build"]["shared_requests"] + repaired.get(
            "shared_requests", []
        )
        return prev

    def check(prev: dict, issue: dict, _i: int) -> dict | None:
        prev["check"] = flow.agent(
            CHECK.format(**fields(issue)),
            label=f"check-{issue['issue']}",
            role="check",
            cwd=prev["path"],
            required={"verdict": "str", "findings": "list"},
            state=flow.head(prev["path"]),
        )
        return prev

    done = flow.pipeline(sl["issues"], build, own, check)
    good = [d for d in done if d]
    failed = [i["issue"] for i, d in zip(sl["issues"], done, strict=True) if not d]

    slice_branch = sl.get("branch") or slug
    slice_path, _ = flow.worktree("slice", base_sha, branch=slice_branch, bootstrap=bootstrap)
    merged = flow.integrate(slice_path, [d["branch"] for d in good])
    checks = [flow.check(cmd, slice_path) for cmd in sl.get("checks", [])]

    report = {
        "epic": sheet["epic"],
        "slice": sl["id"],
        "slice_branch": slice_branch,
        "slice_worktree": slice_path,
        "base": base_sha,
        "merged": merged["merged"],
        "conflicts": merged["conflicts"],
        "failed_issues": failed,
        "checks": checks,
        "shared_requests": [
            {"issue": d["issue"], "request": r} for d in good for r in d["shared_requests"]
        ],
        "open_points": {d["issue"]: d["build"]["open_points"] for d in good},
        "findings": {
            d["issue"]: d["check"]["findings"] if d.get("check") else "Prüfer gescheitert"
            for d in good
        },
    }
    out = run_dir / "slice-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    flow.log(f"Bericht: {out}")
    clean = not (failed or merged["conflicts"] or any(c["rc"] for c in checks))
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
