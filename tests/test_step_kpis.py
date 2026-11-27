"""Die Schritt-KPI-Registry (docs/analysis/step-kpis.json) bleibt konsistent.

Prüft Form und Verweise, nicht die Messwerte: jeder Prozessschritt hat eine
Qualitäts-KPI und eine Geschwindigkeits- oder Kosten-KPI, jede Lücke nennt
ihren Grund, und jeder Pfad zeigt auf eine Datei im Template.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "analysis" / "step-kpis.json"
TEMPLATE = ROOT / "template"

DIMENSIONS = {"quality", "speed", "cost", "guard"}
STATUSES = {"measured", "estimated", "proxy", "missing"}
KENNI_DATA = {"vorhanden", "fehlt", "ungeprüft", "n/a"}
DIRECTIONS = {"lower", "higher", "none"}


def _load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _all_kpis(registry: dict) -> list[dict]:
    return [k for step in registry["steps"] for k in step["kpis"]]


def _template_has(rel: str) -> bool:
    """True when the template ships a file for `rel` (repo-relative path).

    Templates name files with a `.jinja` suffix or a Jinja `{% if %}` prefix,
    so the match is on the basename within the same directory.
    """
    parent, name = Path(rel).parent.as_posix(), Path(rel).name
    return any(
        name in p.name and p.parent.as_posix().endswith(parent)
        for p in TEMPLATE.rglob("*")
        if p.is_file()
    )


def test_registry_loads_and_covers_all_steps():
    registry = _load()
    ids = [s["id"] for s in registry["steps"]]
    assert ids == [f"S{n}" for n in range(1, 18)], "Schrittliste lückenhaft oder unsortiert"
    assert len(set(ids)) == len(ids)


def test_every_step_has_a_quality_and_a_speed_or_cost_kpi():
    for step in _load()["steps"]:
        dims = {k["dimension"] for k in step["kpis"]}
        assert "quality" in dims, f"{step['id']} ohne Qualitäts-KPI"
        assert dims & {"speed", "cost"}, f"{step['id']} ohne Geschwindigkeits- oder Kosten-KPI"


def test_kpi_ids_are_unique_and_prefixed_by_their_step():
    registry = _load()
    seen: set[str] = set()
    for step in registry["steps"]:
        for kpi in step["kpis"]:
            assert kpi["id"].startswith(step["id"] + "."), f"{kpi['id']} nicht unter {step['id']}"
            assert kpi["id"] not in seen, f"doppelte KPI-ID {kpi['id']}"
            seen.add(kpi["id"])


def test_enumerated_fields_hold_allowed_values():
    for kpi in _all_kpis(_load()):
        assert kpi["dimension"] in DIMENSIONS, kpi["id"]
        assert kpi["status"] in STATUSES, kpi["id"]
        assert kpi["kenni_data"] in KENNI_DATA, kpi["id"]
        assert kpi["direction"] in DIRECTIONS, kpi["id"]


def test_missing_or_proxy_kpis_explain_the_gap():
    for kpi in _all_kpis(_load()):
        if kpi["status"] in {"missing", "proxy"}:
            assert kpi.get("gap"), f"{kpi['id']} ({kpi['status']}) ohne Begründung in gap"


def test_measured_kpis_without_kenni_data_name_the_missing_record():
    # Eine als measured geführte KPI, für die kenni keine Daten hat, muss den
    # fehlenden Datensatz im gap nennen.
    for kpi in _all_kpis(_load()):
        if kpi["status"] == "measured" and kpi["kenni_data"] == "fehlt":
            assert kpi.get("gap"), f"{kpi['id']}: measured, aber kenni hat keine Daten und kein gap"


def test_owner_and_instrument_paths_exist_in_the_template():
    registry = _load()
    for step in registry["steps"]:
        owner = step["owner"]
        assert _template_has(owner), f"{step['id']}: Owner {owner} nicht im Template"
    for kpi in _all_kpis(registry):
        instrument = kpi.get("instrument")
        if instrument:
            assert _template_has(instrument), f"{kpi['id']}: Instrument {instrument} fehlt im Template"


def test_backlog_and_goals_reference_existing_kpis():
    registry = _load()
    known = {k["id"] for k in _all_kpis(registry)}
    for item in registry["instrumentation_backlog"]:
        for kpi_id in item["kpi_ids"]:
            assert kpi_id in known, f"{item['id']} verweist auf unbekannte KPI {kpi_id}"
    for goal in registry["goals"]:
        for kpi_id in goal["kpi_ids"]:
            assert kpi_id in known, f"Ziel {goal['name']} verweist auf unbekannte KPI {kpi_id}"


def test_backlog_priorities_are_one_to_three_and_every_kpi_gap_is_planned_or_marked():
    registry = _load()
    planned = {kid for item in registry["instrumentation_backlog"] for kid in item["kpi_ids"]}
    for item in registry["instrumentation_backlog"]:
        assert item["priority"] in {1, 2, 3}, item["id"]
    for kpi in _all_kpis(registry):
        if kpi["status"] == "missing" and kpi["priority"] is None:
            # Ohne Priorität muss die KPI wenigstens im Backlog stehen.
            assert kpi["id"] in planned, f"{kpi['id']}: fehlt, ohne Priorität und ohne Backlog-Eintrag"
