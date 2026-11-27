#!/usr/bin/env python3
"""Vorlage: mehrere unabhängige Entwürfe, dann Kritik an allen.

    python judge_panel.py <auftrag.json> <workers.json> <run-dir>

``auftrag.json``: {"task": "…", "angles": [{"label": "…", "lens": "…"}],
                   "critics": [{"label": "…", "lens": "…"}]}
Die Auswahl trifft danach der steuernde Agent: Er liest ``panel.json`` und
entscheidet selbst, statt das Urteil einem weiteren Arbeiter zu überlassen.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("EPIC_SLICE_HOME") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(HOME / "scripts"))
from flow import Flow

DRAFT = """{task}

Dein Blickwinkel: {lens}
Ändere nichts. Ergebnis: answer (ein Satz), proposal, risks (Liste), unverified (Liste)."""

CRITIC = """{task}

Hier sind {count} Entwürfe:
{drafts}

Versuche sie zu widerlegen. Dein Blickwinkel: {lens}
Prüfe tragende Tatsachenbehauptungen selbst nach, ändere nichts.
Ergebnis: wrong_claims (Liste mit Beleg), holds (welcher Entwurf unter welchen Bedingungen)."""


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    flow = Flow(".", sys.argv[3], sys.argv[2])
    drafts = flow.parallel(
        [
            lambda a=a: flow.agent(
                DRAFT.format(task=job["task"], lens=a["lens"]),
                label=f"draft-{a['label']}",
                role="plan",
                required={
                    "answer": "str",
                    "proposal": "any",
                    "risks": "list",
                    "unverified": "list",
                },
            )
            for a in job["angles"]
        ]
    )
    kept = [d for d in drafts if d]
    out = Path(sys.argv[3]) / "panel.json"
    if not kept:
        out.write_text(json.dumps({"drafts": drafts, "critiques": []}), encoding="utf-8")
        flow.log("kein Entwurf zustande gekommen — keine Kritik gestartet")
        return 1
    text = "\n\n".join(json.dumps(d, ensure_ascii=False, indent=1) for d in kept)
    critiques = flow.parallel(
        [
            lambda c=c: flow.agent(
                CRITIC.format(task=job["task"], count=len(kept), drafts=text, lens=c["lens"]),
                label=f"critic-{c['label']}",
                role="check",
                required={"wrong_claims": "list", "holds": "any"},
            )
            for c in job.get("critics", [])
        ]
    )
    out.write_text(
        json.dumps({"drafts": drafts, "critiques": critiques}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    flow.log(f"{len(kept)} Entwürfe, {len([c for c in critiques if c])} Kritiken — {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
