"""Run a selected signal-control adapter against the integrated CityFlow network."""
from __future__ import annotations

import argparse, bisect, csv, json, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from algorithms import ActuatedPressureAlgorithm, FixedTimeAlgorithm, MaxPressureAlgorithm, TransytStyleAlgorithm, TransytFrapCoordinator

CONTROL_GROUP = {"W": "W", "E": "E", "N": "N", "S": "S", "NW": "N", "NE": "N", "SW": "S", "SE": "S"}


def lane_count(engine, road_id: str, lane: int) -> int:
    return int(engine.get_lane_vehicle_count().get(f"{road_id}_{lane}", 0))


def collect_state(engine, roadnet: dict) -> np.ndarray:
    """Aggregate feeder and upstream connector counts into 12 fixed movement slots."""
    rows = []
    for node in range(1, 21):
        inter = next(i for i in roadnet["intersections"] if i["id"] == f"j_{node:02d}")
        groups = {d: [] for d in "WENS"}
        for rid in inter["roads"]:
            road = next(r for r in roadnet["roads"] if r["id"] == rid)
            if road["endIntersection"] != f"j_{node:02d}": continue
            if rid.startswith("feed_"): groups[CONTROL_GROUP[rid.rsplit("_", 1)[1]]].append(rid)
            elif rid.startswith("link_"):
                # The frozen 4x4 controller accepts cardinal features only.
                # Folded diagonal links are retained by CityFlow and aggregate
                # into their nearest cardinal arrival group for inference.
                departure = rid.split("_")[2]; groups[CONTROL_GROUP[{"W":"E", "E":"W", "N":"S", "S":"N", "NW":"SE", "NE":"SW", "SW":"NE", "SE":"NW"}[departure]]].append(rid)
        values = []
        for d in "WENS":
            left = sum(lane_count(engine, rid, 0) for rid in groups[d]); straight_right = sum(lane_count(engine, rid, 1) for rid in groups[d])
            values += [left, straight_right, straight_right]
        rows.append(values)
    return np.asarray(rows, dtype=np.float32)


def vehicle_snapshot(engine, roadnet: dict, limit: int = 1000) -> list[dict[str, float | str]]:
    """Compact vehicle positions for the host-side live monitor."""
    road_length = {}
    for road in roadnet["roads"]:
        points = road["points"]
        road_length[road["id"]] = sum(((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 for a, b in zip(points, points[1:]))
    result = []
    for vehicle_id in sorted(engine.get_vehicles())[:limit]:
        info = engine.get_vehicle_info(vehicle_id)
        road = info.get("road", "")
        if road:
            route = info.get("route", "").split(); index = route.index(road) if road in route else 0
            local_distance = float(info.get("distance", 0.0)) - sum(road_length.get(item, 0.0) for item in route[:index])
            result.append({"id": vehicle_id, "road": road, "distance": max(0.0, local_distance), "speed": float(info.get("speed", 0.0))})
    return result


def road_lengths(roadnet: dict) -> dict[str, float]:
    return {road["id"]: sum(((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 for a, b in zip(road["points"], road["points"][1:])) for road in roadnet["roads"]}


def build_algorithm(name: str, count: int, checkpoint: Path, grid_positions: list[list[int]] | None = None, min_green: int = 2, max_green: int = 6, switch_ratio: float = 1.10, fixed_offset: int = 0, coordination_override_ratio: float = 1.25, coordination_overload_ratio: float = 0.80, coordination_minimum_gain: float = 2.0, transyt_cycle_decisions: int = 9):
    if name == "fixed": return FixedTimeAlgorithm(count, phase_offset=fixed_offset)
    if name == "fixed_10": return FixedTimeAlgorithm(count, 1, fixed_offset)
    if name == "fixed_20": return FixedTimeAlgorithm(count, 2)
    if name == "fixed_40": return FixedTimeAlgorithm(count, 4)
    if name == "max_pressure": return MaxPressureAlgorithm()
    if name == "actuated_pressure": return ActuatedPressureAlgorithm(count, min_green, max_green, switch_ratio)
    if name in ("transyt", "transyt_style"): return TransytStyleAlgorithm(count, grid_positions, cycle_decisions=transyt_cycle_decisions)
    if name == "ugat_frap_transyt":
        transyt = TransytStyleAlgorithm(count, grid_positions, cycle_decisions=transyt_cycle_decisions)
        frap = build_algorithm("ugat_frap", count, checkpoint, grid_positions, min_green, max_green, switch_ratio, fixed_offset)
        return TransytFrapCoordinator(transyt, frap, min_green_decisions=min_green, override_ratio=coordination_override_ratio, overload_ratio=coordination_overload_ratio, minimum_gain=coordination_minimum_gain)
    if name in ("ugat_transyt", "frap_transyt"):
        transyt = TransytStyleAlgorithm(count, grid_positions, cycle_decisions=transyt_cycle_decisions)
        branch = "ugat_only" if name == "ugat_transyt" else "frap_only"
        controller = TransytFrapCoordinator(transyt, build_algorithm(branch, count, checkpoint, grid_positions, min_green, max_green, switch_ratio, fixed_offset), min_green_decisions=min_green, override_ratio=coordination_override_ratio, overload_ratio=coordination_overload_ratio, minimum_gain=coordination_minimum_gain)
        controller.name = name
        return controller
    if name in ("ugat_frap", "ugat_only", "frap_only"):
        import torch
        from ugat_frap import UGATFRAPController
        # The two ablations keep the exact same checkpoint and inference path,
        # changing only one branch's contribution to the fused Q values.
        branch_weight = {"ugat_frap": 1.0, "ugat_only": 0.0, "frap_only": 1.0}[name]
        model = UGATFRAPController(checkpoint, max_frap_weight=branch_weight); adapter = ROOT / "model" / "frap_adapter.pt"
        if adapter.exists(): model.load_adapter(adapter)
        model.assert_frozen(); model.eval()
        algorithm_name = name
        class TorchAdapter:
            def __init__(self):
                self.current_actions = np.zeros(count, dtype=np.int64); self.decision_count = 0; self.schedule_offset = None; self.phase_durations = None
            def choose(self, state):
                # The frozen 4x4 network expects 12 lane values followed by 8 phase flags.
                # Feed the actual phase selected at the previous decision, rather than
                # assuming phase 0 is always active.
                phase = np.zeros((len(state), 8), dtype=np.float32)
                phase[np.arange(len(state)), self.current_actions] = 1
                model_state = torch.from_numpy(np.concatenate((state, phase), axis=1))
                if algorithm_name == "frap_only":
                    # Remove UGAT contribution while preserving the trained FRAP adapter.
                    q = model.frap(torch.cat((model_state[:, 12:], model_state[:, :12]), dim=1))
                    actions = q.argmax(dim=1).cpu().numpy()
                elif algorithm_name == "ugat_only":
                    actions = model.choose_actions(model_state).cpu().numpy()
                else:
                    # The supplied UGAT checkpoint and FRAP adapter have very
                    # different Q scales (hundreds versus fractions). Normalize
                    # each branch per state before fusion; add a pressure residual
                    # as a safety signal for unseen 20-intersection demand.
                    ugat_q = model.ugat(model_state)
                    frap_q = model.frap(torch.cat((model_state[:, 12:], model_state[:, :12]), dim=1))
                    pressure_pairs = ((1, 4), (7, 10), (0, 3), (6, 9), (0, 1), (3, 4), (9, 10), (6, 7))
                    pressure_q = torch.stack([model_state[:, list(pair)].sum(dim=1) for pair in pressure_pairs], dim=1)
                    def zscore(x): return (x - x.mean(dim=1, keepdim=True)) / (x.std(dim=1, keepdim=True) + 1e-6)
                    fused_q = zscore(ugat_q) + 0.5 * zscore(frap_q) + 1.0 * zscore(pressure_q)
                    candidate = fused_q.argmax(dim=1).cpu().numpy()
                    # Stable demand-weighted schedule is the prior; switch only
                    # when pressure gain is materially larger than that phase.
                    if self.schedule_offset is None:
                        pressure_init = pressure_q.detach().cpu().numpy()
                        self.schedule_offset = pressure_init.argmax(axis=1).astype(np.int64)
                        scale = pressure_init / np.maximum(pressure_init.mean(axis=1, keepdims=True), 1e-6)
                        self.phase_durations = np.clip(np.rint(3.0 * scale).astype(np.int64), 1, 8)
                    fixed_action = np.empty(count, dtype=np.int64)
                    for row in range(count):
                        durations = self.phase_durations[row]; cycle = int(durations.sum()); slot = self.decision_count % cycle; phase = int(self.schedule_offset[row])
                        for _ in range(8):
                            duration = int(durations[phase])
                            if slot < duration: break
                            slot -= duration; phase = (phase + 1) % 8
                        fixed_action[row] = phase
                    pressure_np = pressure_q.cpu().numpy()
                    pressure_z = (pressure_np - pressure_np.mean(axis=1, keepdims=True)) / (pressure_np.std(axis=1, keepdims=True) + 1e-6)
                    gain = pressure_z[np.arange(len(state)), candidate] - pressure_z[np.arange(len(state)), fixed_action]
                    actions = np.where(gain > 0.15, candidate, fixed_action)
                    self.decision_count += 1
                self.current_actions = actions.astype(np.int64, copy=False)
                return actions
        adapter_controller = TorchAdapter()
        adapter_controller.name = algorithm_name
        return adapter_controller
    raise ValueError(f"Unsupported algorithm {name}")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--period", choices=("morning", "midday", "evening"), default="morning")
    ap.add_argument("--flow-file", default=None, help="Optional flow JSON in data/xiong_an_20, e.g. flow_midday_pressure30.json")
    ap.add_argument("--algorithm", choices=("fixed", "fixed_10", "fixed_20", "fixed_40", "max_pressure", "actuated_pressure", "transyt", "transyt_style", "ugat_frap", "ugat_transyt", "frap_transyt", "ugat_frap_transyt", "ugat_only", "frap_only"), default="ugat_frap")
    ap.add_argument("--steps", type=int, default=7500); ap.add_argument("--decision-interval", type=int, default=10); ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs"); ap.add_argument("--live-trace", type=Path, default=None); ap.add_argument("--visual-delay-ms", type=int, default=0); ap.add_argument("--live-interval", type=int, default=10)
    ap.add_argument("--min-green-decisions", type=int, default=1); ap.add_argument("--max-green-decisions", type=int, default=6); ap.add_argument("--switch-ratio", type=float, default=1.10); ap.add_argument("--fixed-offset", type=int, choices=range(8), default=0)
    ap.add_argument("--coordination-override-ratio", type=float, default=1.05); ap.add_argument("--coordination-overload-ratio", type=float, default=0.95); ap.add_argument("--coordination-minimum-gain", type=float, default=1.0)
    ap.add_argument("--transyt-cycle-decisions", type=int, default=9); args = ap.parse_args()
    try: import cityflow
    except ImportError as exc: raise SystemExit("CityFlow is required for runtime. Use Docker or install cityflow in Linux.") from exc
    data = ROOT / "data" / "xiong_an_20"; config = json.loads((data / "cityflow.config.json").read_text(encoding="utf-8")); config["flowFile"] = args.flow_file or f"flow_{args.period}.json"; config["dir"] = str(data.resolve()).replace("\\", "/") + "/"
    if not (data / config["flowFile"]).is_file():
        raise SystemExit(f"Flow file not found: {data / config['flowFile']}")
    args.out_dir.mkdir(parents=True, exist_ok=True); runtime_config = args.out_dir / f"cityflow_{args.period}.json"; runtime_config.write_text(json.dumps(config, indent=2), encoding="utf-8")
    engine = cityflow.Engine(str(runtime_config), thread_num=args.threads); roadnet = json.loads((data / "roadnet.json").read_text(encoding="utf-8")); flow = json.loads((data / config["flowFile"]).read_text(encoding="utf-8")); departures = sorted(item["startTime"] for item in flow)
    topology = json.loads((data / "topology.json").read_text(encoding="utf-8")); grid_positions = [topology["positions"][str(node)] for node in range(1, 21)]
    lengths = road_lengths(roadnet)
    freeflow_times = [sum(lengths.get(r, 0.0) for r in item["route"]) / max(float(item["vehicle"].get("maxSpeed", 13.89)), 1e-6) for item in flow]
    freeflow_mean = float(np.mean(freeflow_times)) if freeflow_times else 0.0
    controller = build_algorithm(args.algorithm, 20, ROOT / "model" / "frozen_ugat_4x4.pt", grid_positions, args.min_green_decisions, args.max_green_decisions, args.switch_ratio, args.fixed_offset, args.coordination_override_ratio, args.coordination_overload_ratio, args.coordination_minimum_gain, args.transyt_cycle_decisions); trace = []; started = time.perf_counter()
    live_path = args.live_trace or args.out_dir / f"live_{args.algorithm}_{args.period}.jsonl"; live_path.parent.mkdir(parents=True, exist_ok=True)
    with live_path.open("w", encoding="utf-8") as live:
        actions = np.zeros(20, dtype=np.int64)
        for tick in range(args.steps):
            if tick % args.decision_interval == 0:
                state = collect_state(engine, roadnet); actions = controller.choose(state)
                for node, action in enumerate(actions, start=1): engine.set_tl_phase(f"j_{node:02d}", int(action) + 1)
            if tick % args.live_interval == 0:
                display_state = collect_state(engine, roadnet)
                scheduled = bisect.bisect_right(departures, tick); active = int(engine.get_vehicle_count()); completed = max(0, scheduled - active); avg_tt = float(engine.get_average_travel_time())
                record = {"time_s": tick, "active_vehicles": active, "scheduled_vehicles": scheduled, "completed_vehicles_est": completed, "throughput_est": completed / max(scheduled, 1), "total_demand": len(departures), "queue_proxy": int(display_state.sum()), "node_queue_proxy": display_state.sum(axis=1).astype(int).tolist(), "average_travel_time_s": avg_tt, "estimated_delay_s": max(0.0, avg_tt - freeflow_mean), "actions": actions.tolist(), "vehicles": vehicle_snapshot(engine, roadnet)}
                trace.append(record); live.write(json.dumps(record, ensure_ascii=False) + "\n"); live.flush()
            if tick % args.decision_interval == 0:
                if args.visual_delay_ms > 0: time.sleep(args.visual_delay_ms / 1000.0)
            engine.next_step()
    elapsed = time.perf_counter() - started; final = trace[-1] if trace else {"active_vehicles": 0, "queue_proxy": 0}
    metrics = {"algorithm": controller.name, "period": args.period, "steps": args.steps, "wall_seconds": round(elapsed, 3), "steps_per_second": round(args.steps / max(elapsed, 1e-9), 2), "total_demand": len(departures), "scheduled_vehicles": final.get("scheduled_vehicles", 0), "completed_vehicles_est": final.get("completed_vehicles_est", 0), "throughput_est": round(final.get("throughput_est", 0.0), 6), "final_active_vehicles": final["active_vehicles"], "final_queue_proxy": final["queue_proxy"], "average_travel_time_s": round(final.get("average_travel_time_s", 0.0), 3), "estimated_delay_s": round(final.get("estimated_delay_s", 0.0), 3), "freeflow_mean_s": round(freeflow_mean, 3)}
    if hasattr(controller, "coordination_metrics"): metrics.update(controller.coordination_metrics())
    with live_path.open("a", encoding="utf-8") as live: live.write(json.dumps({"status": "complete", "metrics": metrics}, ensure_ascii=False) + "\n")
    (args.out_dir / f"trace_{args.algorithm}_{args.period}.json").write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    path = args.out_dir / "metrics.csv"; exists = path.exists()
    existing_fields = []
    if exists:
        with path.open(newline="", encoding="utf-8") as handle:
            existing_fields = (csv.DictReader(handle).fieldnames or [])
    fields = list(dict.fromkeys(existing_fields + list(metrics)))
    if exists and fields != existing_fields:
        with path.open(newline="", encoding="utf-8") as handle:
            old_rows = []
            for row in csv.DictReader(handle):
                row.pop(None, None)
                old_rows.append({key: row.get(key, "") for key in existing_fields})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(old_rows)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writerow(metrics)
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__": main()
