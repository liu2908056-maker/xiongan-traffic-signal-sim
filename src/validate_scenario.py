"""Fast static validation for reproducible pre-CityFlow checks."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data" / "xiong_an_20"


def main() -> None:
    roadnet = json.loads((DATA / "roadnet.json").read_text(encoding="utf-8")); roads = {r["id"]: r for r in roadnet["roads"]}
    controls = [i for i in roadnet["intersections"] if not i["virtual"]]
    assert len(controls) == 20, f"expected 20 controls, got {len(controls)}"
    assert all(len(i["trafficLight"]["lightphases"]) == 9 for i in controls), "every controller must have 8 actions + clearance phase"
    transitions = {}
    for i in roadnet["intersections"]:
        transitions[i["id"]] = {(link["startRoad"], link["endRoad"]) for link in i["roadLinks"]}
    for i in controls:
        for link in i["roadLinks"]:
            assert link["startRoad"] in roads and link["endRoad"] in roads, f"bad link at {i['id']}"
    totals = {}
    for period in ("morning", "midday", "evening"):
        flow = json.loads((DATA / f"flow_{period}.json").read_text(encoding="utf-8")); assert flow, f"empty {period} flow"
        for vehicle in flow:
            assert vehicle["route"] and all(r in roads for r in vehicle["route"]), "flow contains unknown road"
            for start, end in zip(vehicle["route"], vehicle["route"][1:]):
                junction = roads[start]["endIntersection"]
                assert (start, end) in transitions[junction], f"invalid route transition {start} -> {end} at {junction}"
            assert vehicle["startTime"] >= 0 and vehicle["endTime"] >= 0, "negative departure"
            assert vehicle["vehicle"]["type"] in {"car", "bus", "freight"}, "unknown vehicle type"
        totals[period] = len(flow)
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8")); assert len(manifest) == 20, "manifest must include all source workbooks"
    expected = {p: sum(item["periods"][p]["vehicles"] for item in manifest) for p in totals}; assert expected == totals, f"flow totals mismatch {expected} != {totals}"
    audit = json.loads((DATA / "excel_audit.json").read_text(encoding="utf-8"))
    assert set(audit) == {str(node) for node in range(1, 21)}, "Excel audit must cover all 20 workbooks"
    for period in totals:
        by_input = Counter()
        flow = json.loads((DATA / f"flow_{period}.json").read_text(encoding="utf-8"))
        for vehicle in flow:
            first = vehicle["route"][0]
            assert first.startswith("feed_"), f"flow must start at an Excel feeder: {first}"
            _, node, approach = first.split("_")
            by_input[(str(int(node)), approach)] += 1
        for node, item in audit.items():
            audit_period = item["periods"][period]
            assert audit_period["excel_total"] == audit_period["generated_total"], f"Excel generation mismatch at J{node} {period}"
            assert sum(audit_period["approach_vehicles"].values()) == audit_period["excel_total"], f"Excel approach mismatch at J{node} {period}"
            for approach, count in audit_period["approach_vehicles"].items():
                assert by_input[(node, approach)] == count, f"flow approach mismatch at J{node} {approach} {period}"
    print(json.dumps({"status": "PASS", "controlled_intersections": len(controls), "roads": len(roads), "flow_vehicles": totals, "excel_alignment": "20/20 workbooks, directions and vehicle totals matched"}, ensure_ascii=False))


if __name__ == "__main__": main()
