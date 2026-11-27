#!/usr/bin/env python3
"""Vorlage: finden, dann jeden Fund von Unbeteiligten widerlegen lassen.

    python find_verify.py <auftrag.json> <workers.json> <run-dir>

``auftrag.json``: {"finders": [{"label": "…", "prompt": "…"}], "votes": 2}
Finder liefern ``findings`` (Liste aus Objekten mit ``claim`` und ``where``).
Je Fund versuchen ``votes`` Arbeiter, ihn zu widerlegen. Er bleibt, wenn die
Mehrheit der gültigen Stimmen ihn nicht widerlegt; ohne gültige Stimme gilt er
als ungeprüft und steht so im Bericht. Die Arbeiter sollen nur lesen; das
steht im Auftrag, erzwungen wird es nicht.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("EPIC_SLICE_HOME") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(HOME / "scripts"))
from flow import Flow

REFUTE = """Versuche diese Behauptung zu widerlegen. Lies die Stelle selbst nach, ändere nichts.
Behauptung: {claim}
Ort: {where}
Bist du unsicher, gilt sie als widerlegt.
Ergebnis: refuted (true oder false als JSON-Wahrheitswert), reason."""


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    flow = Flow(".", sys.argv[3], sys.argv[2])
    votes = int(job.get("votes", 2))

    def find(_prev: dict, finder: dict, _i: int) -> list:
        result = flow.agent(
            finder["prompt"] + "\nÄndere nichts. Ergebnis: findings (Liste aus claim und where).",
            label=f"find-{finder['label']}",
            role="check",
            required={"findings": "list"},
        )
        return result["findings"] if result else []

    found = [f for group in flow.pipeline(job["finders"], find) for f in (group or [])]
    usable = [f for f in found if isinstance(f, dict) and f.get("claim")]
    if len(usable) < len(found):
        flow.log(f"{len(found) - len(usable)} Funde ohne claim verworfen")
    seen: set[tuple[str, str]] = set()
    unique = []
    for f in usable:
        key = (str(f.get("where")), str(f["claim"]))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    def verify(_prev: dict, finding: dict, i: int) -> dict:
        ballots = flow.parallel(
            [
                lambda v=v: flow.agent(
                    REFUTE.format(claim=finding["claim"], where=finding.get("where")),
                    label=f"refute-{i}-{v}",
                    role="check",
                    required={"refuted": "bool", "reason": "str"},
                )
                for v in range(votes)
            ]
        )
        valid = [b for b in ballots if b]
        if not valid:
            status = "ungeprüft"
            flow.log(f"Fund {i}: keine gültige Stimme — ungeprüft")
        else:
            kept = [b for b in valid if not b["refuted"]]
            status = "bestätigt" if len(kept) * 2 > len(valid) else "widerlegt"
        return {**finding, "status": status, "ballots": ballots}

    judged = [j for j in flow.pipeline(unique, verify) if j]
    report = {s: [j for j in judged if j["status"] == s] for s in ("bestätigt", "ungeprüft")}
    report["all"] = judged
    out = Path(sys.argv[3]) / "findings.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    flow.log(
        f"{len(report['bestätigt'])} bestätigt, {len(report['ungeprüft'])} ungeprüft "
        f"von {len(unique)} Funden — {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
