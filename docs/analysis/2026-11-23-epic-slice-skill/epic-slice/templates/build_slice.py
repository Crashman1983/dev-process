#!/usr/bin/env python3
"""Vorlage: eine Scheibe parallel bauen, je Issue prüfen, lokal zusammenführen.

    python build_slice.py <epic-blatt.md> <scheiben-id> <workers.json> [<run-dir>]

Eine Vorlage, kein fester Ablauf: Der steuernde Agent kopiert sie in den
Lauf-Ordner und ändert sie für die Aufgabe (weitere Stufen, eine zweite
Korrekturrunde, andere Rollen). Was sie am Ende hinterlässt, ist ein
zusammengeführter lokaler Zweig und ``slice-report.json`` für den
Integrationsowner. Landen auf main ist nicht Teil davon.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from flow import Flow, load_sheet

BUILD = """Du baust Issue #{issue} ({title}) als Teil des Epics {epic}.

Referenz: {ref_build}. Prüfe zuerst, dass du sie hast: {ref_check}
Stimmt die Referenz nicht, hör auf und melde das in "open_points".

Dir gehören nur diese Dateien: {owns}
Gemeinsame Dateien ({shared}) änderst du nicht. Brauchst du dort etwas,
beschreibe es in "shared_requests" (Datei, gewünschte Änderung, Grund).
Querschnittsverhalten mit festem Owner, das du nicht änderst: {cross}

Akzeptanzkriterien stehen im Issue #{issue}. Schreibe je Kriterium einen Test,
führe diese Tests aus: {tests}
Committe in deinem Arbeitsverzeichnis mit der Issue-Nummer im Betreff.

Ergebnis: summary, tests_run (Befehl und Ausgang), shared_requests (Liste),
open_points (Liste; leer, wenn nichts offen ist)."""

REPAIR = """Dein Zweig für Issue #{issue} ändert Dateien, die dir nicht gehören: {foreign}
Nimm diese Änderungen zurück. Was du dort brauchst, gehört in "shared_requests".
Committe die Korrektur. Ergebnis: summary, shared_requests, open_points."""

CHECK = """Prüfe den Stand in diesem Arbeitsverzeichnis gegen Issue #{issue} ({title}).
Du hast ihn nicht gebaut. Lies das Issue und den Diff gegen {base}.
Nenne nur, was ein Kriterium verfehlt oder kaputt ist; Stilfragen nicht.
Führe aus: {tests}
Ergebnis: verdict ("ok" oder "findings"), findings (Liste aus Datei, Zeile, Befund)."""


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
    run_dir = sys.argv[4] if len(sys.argv) > 4 else f".process-work/flow/{slug}"
    flow = Flow(".", run_dir, sys.argv[3], max_parallel=sl.get("max_parallel", 4))
    shared = sheet.get("shared_paths", [])
    cross = "; ".join(f"{c['behavior']} → {c['owner']}" for c in sheet.get("cross_cutting", []))
    base = sl["base"]

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

    def build(_prev: dict, issue: dict, _i: int) -> dict | None:
        path, branch = flow.worktree(f"issue-{issue['issue']}", base)
        result = flow.agent(
            BUILD.format(**fields(issue)),
            label=f"build-{issue['issue']}",
            role="build",
            cwd=path,
            required=("summary", "tests_run", "shared_requests", "open_points"),
        )
        return result and {"issue": issue["issue"], "path": path, "branch": branch, "build": result}

    def own(prev: dict, issue: dict, _i: int) -> dict | None:
        outside = flow.ownership(prev["branch"], base, issue["owns"], shared)
        touched = outside["foreign"] + outside["shared"]
        if touched:
            repair = flow.agent(
                REPAIR.format(issue=issue["issue"], foreign=", ".join(touched)),
                label=f"repair-{issue['issue']}",
                role="build",
                cwd=prev["path"],
                required=("summary", "shared_requests", "open_points"),
            )
            outside = flow.ownership(prev["branch"], base, issue["owns"], shared)
            if repair is None or outside["foreign"] or outside["shared"]:
                flow.log(
                    f"#{issue['issue']}: fasst weiter fremde Dateien an — nicht zusammengeführt"
                )
                return None
            prev["build"]["shared_requests"] += repair["shared_requests"]
        return prev

    def check(prev: dict, issue: dict, _i: int) -> dict | None:
        prev["check"] = flow.agent(
            CHECK.format(**fields(issue)),
            label=f"check-{issue['issue']}",
            role="check",
            cwd=prev["path"],
            required=("verdict", "findings"),
        )
        return prev

    done = flow.pipeline(sl["issues"], build, own, check)
    good = [d for d in done if d]
    failed = [i["issue"] for i, d in zip(sl["issues"], done, strict=True) if not d]

    slice_path, slice_branch = flow.worktree("slice", base)
    merged = flow.integrate(slice_path, [d["branch"] for d in good])
    checks = [flow.check(cmd, slice_path) for cmd in sl.get("checks", [])]

    report = {
        "epic": sheet["epic"],
        "slice": sl["id"],
        "slice_branch": slice_branch,
        "merged": merged["merged"],
        "conflicts": merged["conflicts"],
        "failed_issues": failed,
        "checks": checks,
        "shared_requests": [
            {"issue": d["issue"], **r} if isinstance(r, dict) else {"issue": d["issue"], "text": r}
            for d in good
            for r in d["build"]["shared_requests"]
        ],
        "open_points": {d["issue"]: d["build"]["open_points"] for d in good},
        "findings": {
            d["issue"]: d["check"]["findings"] if d.get("check") else "Prüfer gescheitert"
            for d in good
        },
    }
    out = Path(run_dir) / "slice-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    flow.log(f"Bericht: {out}")
    clean = not (failed or merged["conflicts"] or any(c["rc"] for c in checks))
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
