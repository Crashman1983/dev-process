#!/usr/bin/env python3
"""Vorlage: finden, dann jeden Fund von Unbeteiligten widerlegen lassen.

    python find_verify.py <auftrag.json> <workers.json> <run-dir>

``auftrag.json``: {"finders": [{"label": "…", "prompt": "…"}], "votes": 2}
Finder liefern ``findings`` (Liste aus ``claim`` und ``where``). Je Fund
versuchen ``votes`` Arbeiter, ihn zu widerlegen; er bleibt, wenn die Mehrheit
ihn nicht widerlegt. Läuft im Repo, schreibt nichts außer dem Bericht.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from flow import Flow

REFUTE = """Versuche diese Behauptung zu widerlegen. Lies die Stelle selbst nach.
Behauptung: {claim}
Ort: {where}
Bist du unsicher, gilt sie als widerlegt.
Ergebnis: refuted (true/false), reason."""


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    flow = Flow(".", sys.argv[3], sys.argv[2])
    votes = int(job.get("votes", 2))

    def find(_prev: dict, finder: dict, _i: int) -> list:
        result = flow.agent(
            finder["prompt"], label=f"find-{finder['label']}", role="check", required=("findings",)
        )
        return result["findings"] if result else []

    found = [f for group in flow.pipeline(job["finders"], find) for f in (group or [])]
    seen: set[tuple[str, str]] = set()
    unique = []
    for f in found:
        key = (str(f.get("where")), str(f.get("claim")))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    def verify(_prev: dict, finding: dict, i: int) -> dict:
        ballots = flow.parallel(
            [
                lambda v=v: flow.agent(
                    REFUTE.format(claim=finding.get("claim"), where=finding.get("where")),
                    label=f"refute-{i}-{v}",
                    role="check",
                    required=("refuted", "reason"),
                )
                for v in range(votes)
            ]
        )
        kept = [b for b in ballots if b and not b["refuted"]]
        return {**finding, "survives": len(kept) * 2 > votes, "ballots": ballots}

    judged = flow.pipeline(unique, verify)
    report = {"confirmed": [j for j in judged if j and j["survives"]], "all": judged}
    out = Path(sys.argv[3]) / "findings.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    flow.log(f"{len(report['confirmed'])} von {len(unique)} Funden halten — {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
