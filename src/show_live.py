"""Native live CityFlow network monitor driven by the runner JSONL stream."""
from __future__ import annotations

import argparse
import json
import math
import tkinter as tk
import time
from pathlib import Path
from tkinter import ttk


LABEL_OFFSETS = {
    7: (-70, -52), 1: (34, -50), 4: (34, -50), 8: (34, -50), 10: (32, -50),
    5: (-78, 40), 6: (32, 40), 3: (32, 40), 2: (32, 40), 9: (34, 40),
    13: (-82, -52), 11: (32, -52), 12: (32, -52), 16: (32, -52), 20: (32, -52),
    14: (-78, 40), 17: (32, 40), 15: (-90, 40), 18: (34, 40), 19: (34, 40),
}


class LiveMonitor:
    def __init__(self, root: tk.Tk, trace_path: Path, roadnet_path: Path, topology_path: Path):
        self.root, self.trace_path, self.offset, self.last = root, trace_path, 0, None
        self.previous, self.frame_started, self.pending = None, time.monotonic(), []
        self.complete_metrics = None
        roadnet = json.loads(roadnet_path.read_text(encoding="utf-8")); self.roads = {r["id"]: r["points"] for r in roadnet["roads"]}
        topology = json.loads(topology_path.read_text(encoding="utf-8")); self.labels = {int(k): v for k, v in topology["labels"].items()}; self.short_labels = {int(k): v for k, v in topology["short_labels"].items()}; self.observed = {int(k): set(v) for k, v in topology["observed_approaches"].items()}; self.neighbors = {int(k): {d: int(target) for d, target in values.items()} for k, values in topology["neighbors"].items()}; self.corridors = topology.get("corridor_roads", []); self.hidden_pairs = {tuple(sorted(pair)) for pair in topology.get("hidden_corridor_pairs", [])}; self.feeder_visual_links = topology.get("feeder_visual_links", {})
        self.road_lengths = {road_id: sum(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(points, points[1:])) for road_id, points in self.roads.items()}
        self.bounds = self._bounds(); self.zoom, self.pan, self.drag = 1.0, [0.0, 0.0], None; self.canvas = tk.Canvas(root, width=1050, height=720, bg="#f8fafc", highlightthickness=0); self.canvas.pack(fill=tk.BOTH, expand=True)
        self.info = ttk.Label(root, text="Waiting for CityFlow live data...", padding=8, font=("Microsoft YaHei", 11)); self.info.pack(fill=tk.X)
        self.canvas.bind("<MouseWheel>", self.on_wheel); self.canvas.bind("<ButtonPress-1>", self.on_press); self.canvas.bind("<B1-Motion>", self.on_drag)
        root.title("Xiong'an 20-Junction CityFlow Live Monitor"); root.geometry("1050x790"); root.minsize(800, 620)
        self.root.update_idletasks(); self.draw({"time_s": 0, "active_vehicles": 0, "scheduled_vehicles": 0, "total_demand": 0, "queue_proxy": 0, "node_queue_proxy": [], "actions": [], "vehicles": []}); self.info.configure(text="Preparing CityFlow stream...")
        self.poll(); self.play()

    def _bounds(self):
        points = [p for road in self.roads.values() for p in road]; xs, ys = [p["x"] for p in points], [p["y"] for p in points]
        return min(xs), max(xs), min(ys), max(ys)

    def xy(self, point):
        x0, x1, y0, y1 = self.bounds; width, height, margin = max(800, self.canvas.winfo_width()), max(620, self.canvas.winfo_height()), 55
        x = margin + (point["x"] - x0) / max(1, x1 - x0) * (width - 2 * margin); y = height - margin - (point["y"] - y0) / max(1, y1 - y0) * (height - 2 * margin)
        return (x - width / 2) * self.zoom + width / 2 + self.pan[0], (y - height / 2) * self.zoom + height / 2 + self.pan[1]

    def on_wheel(self, event):
        self.zoom = max(0.45, min(4.0, self.zoom * (1.12 if event.delta > 0 else 1 / 1.12)))
        if self.last: self.draw(self.last)

    def on_press(self, event): self.drag = (event.x, event.y)

    def on_drag(self, event):
        if self.drag:
            self.pan[0] += event.x - self.drag[0]; self.pan[1] += event.y - self.drag[1]; self.drag = (event.x, event.y)
            if self.last: self.draw(self.last)

    def poll(self):
        if self.trace_path.exists():
            if self.trace_path.stat().st_size < self.offset:
                self.offset = 0
            with self.trace_path.open(encoding="utf-8") as handle:
                handle.seek(self.offset); lines = handle.readlines(); self.offset = handle.tell()
            for line in lines:
                item = json.loads(line)
                if "time_s" in item:
                    self.pending.append(item)
                elif item.get("status") == "complete": self.complete_metrics = item["metrics"]
        self.root.after(60, self.poll)

    def play(self):
        if self.pending:
            self.previous, self.last, self.frame_started = self.last, self.pending.pop(0), time.monotonic()
        if self.last:
            if self.complete_metrics and not self.pending:
                self.last["complete"] = True; self.last["metrics"] = self.complete_metrics
            self.draw(self.last)
        self.root.after(30, self.play)

    def point_on_road(self, road_id, distance):
        points = self.roads.get(road_id)
        if not points:
            return None
        remaining = max(0.0, min(float(distance), self.road_lengths[road_id]))
        for a, b in zip(points, points[1:]):
            length = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            if remaining <= length:
                ratio = remaining / max(1.0, length)
                return {"x": a["x"] + (b["x"] - a["x"]) * ratio, "y": a["y"] + (b["y"] - a["y"]) * ratio}
            remaining -= length
        return points[-1]

    def visible_vehicle_point(self, vehicle):
        """Map hidden local entry roads onto their matching displayed corridor."""
        road_id = vehicle["road"]
        if road_id.startswith("exit_"):
            # The rendered network ends at its boundary; removing a vehicle as
            # it exits is clearer than leaving a dot on an invisible egress.
            return None
        if road_id in self.feeder_visual_links:
            connector = self.feeder_visual_links[road_id]
            if connector in self.roads:
                return self.point_on_road(connector, vehicle["distance"])
        if road_id.startswith("feed_"):
            _, raw_node, direction = road_id.split("_"); node = int(raw_node)
            neighbor = self.neighbors.get(node, {}).get(direction)
            if neighbor is not None:
                opposite = {"W": "E", "E": "W", "N": "S", "S": "N", "NW": "SE", "NE": "SW", "SW": "NE", "SE": "NW"}[direction]
                connector = f"link_{neighbor:02d}_{opposite}_{node:02d}"
                if connector in self.roads:
                    # Both roads finish at this junction. Align the last part
                    # of the hidden feeder with the visible main-road segment.
                    distance = self.road_lengths[connector] - self.road_lengths[road_id] + vehicle["distance"]
                    return self.point_on_road(connector, distance)
        return self.point_on_road(road_id, vehicle["distance"])

    def draw(self, data):
        self.canvas.delete("all")
        # CityFlow represents every direction and external flow feeder as a
        # separate road. Draw paired directions once as a physical corridor;
        # otherwise the internal demand edges look like a four-corner flower.
        corridor_ids = self.corridors or [[road_id] for road_id in self.roads if road_id.startswith("link_")]
        for group in corridor_ids:
            points = self.roads.get(group[0])
            if not points: continue
            parts = group[0].split("_")
            if len(parts) == 4 and tuple(sorted((int(parts[1]), int(parts[3])))) in self.hidden_pairs: continue
            coords = [value for point in points for value in self.xy(point)]
            self.canvas.create_line(*coords, fill="#475569", width=18, joinstyle=tk.ROUND)
            self.canvas.create_line(*coords, fill="#fbbf24", width=1, joinstyle=tk.ROUND)
        # Draw only approaches observed in the supplied traffic table. Missing
        # approaches therefore read as T and two-arm intersections, not crosses.
        for node in range(1, 21):
            for direction in self.observed.get(node, set()):
                # A grid connector already renders this direction. Drawing its
                # local flow feeder too creates the false parallel "flower".
                feeder_id = f"feed_{node:02d}_{direction}"
                if direction in self.neighbors.get(node, {}) or feeder_id in self.feeder_visual_links: continue
                points = self.roads.get(feeder_id)
                if not points: continue
                coords = [value for point in reversed(points) for value in self.xy(point)]
                self.canvas.create_line(*coords, fill="#475569", width=16, joinstyle=tk.ROUND)
                self.canvas.create_line(*coords, fill="#fbbf24", width=1, joinstyle=tk.ROUND)
        actions, queues = data.get("actions", []), data.get("node_queue_proxy", [])
        for node in range(1, 21):
            x, y = self.xy({"x": ((node - 1) % 5) * 420.0, "y": ((node - 1) // 5) * 420.0})
            # Actual model layout is non-sequential; find the junction center from any incident road endpoint.
            jid = f"j_{node:02d}"; centers = [p[-1] for rid, p in self.roads.items() if rid.startswith(f"feed_{node:02d}_")]
            if centers: x, y = self.xy(centers[0])
            action = actions[node - 1] if len(actions) >= node else 0; color = ("#16a34a", "#22c55e", "#65a30d", "#ca8a04", "#ea580c", "#dc2626", "#7c3aed", "#0891b2")[action]
            self.canvas.create_oval(x - 17, y - 17, x + 17, y + 17, fill=color, outline="#ffffff", width=2); self.canvas.create_text(x, y, text=str(node), fill="white", font=("Arial", 9, "bold"))
            dx, dy = LABEL_OFFSETS.get(node, (32, 40)); lx, ly = x + dx, y + dy; queue = queues[node - 1] if len(queues) >= node else 0
            label = f"J{node:02d} {self.short_labels.get(node, '')}\nqueue={queue}"
            width = max(78, len(label.split("\n")[0]) * 6 + 10)
            self.canvas.create_rectangle(lx - 3, ly - 2, lx + width, ly + 24, fill="#f8fafc", outline="")
            self.canvas.create_text(lx, ly, text=label, anchor=tk.NW, fill="#243b53", font=("Microsoft YaHei", 7), justify=tk.LEFT)
        prior = {item.get("id"): item for item in (self.previous or {}).get("vehicles", []) if item.get("id")}
        alpha = min(1.0, (time.monotonic() - self.frame_started) / 0.03)
        for vehicle in data.get("vehicles", []):
            point = self.visible_vehicle_point(vehicle)
            before = prior.get(vehicle.get("id"))
            if before and before.get("road") == vehicle.get("road"):
                old_point = self.visible_vehicle_point(before)
                if old_point and point:
                    point = {"x": old_point["x"] + (point["x"] - old_point["x"]) * alpha, "y": old_point["y"] + (point["y"] - old_point["y"]) * alpha}
            if point is None: continue
            if before:
                trail = self.visible_vehicle_point(before)
                if trail:
                    tx, ty = self.xy(trail); self.canvas.create_oval(tx - 1, ty - 1, tx + 1, ty + 1, fill="#93c5fd", outline="")
            x, y = self.xy(point); color = "#0f766e" if vehicle.get("speed", 0.0) > 0.3 else "#1d4ed8"
            self.canvas.create_oval(x - 1.6, y - 1.6, x + 1.6, y + 1.6, fill=color, outline="")
        injection_complete = bool(data.get("demand_complete") or data.get("injection_complete") or data.get("phase") == "draining" or (data.get("total_demand", 0) > 0 and data.get("scheduled_vehicles", 0) >= data.get("total_demand", 0)))
        if data.get("complete"):
            suffix = "  COMPLETE"
        elif injection_complete:
            suffix = "  DRAINING (injection complete)"
        else:
            suffix = "  INJECTING"
        self.info.configure(text=f"simulation time={data['time_s']} s | demand end={data.get('demand_end_time_s', '?')} s | on-network={data['active_vehicles']} | injected={data.get('scheduled_vehicles', 0)}/{data.get('total_demand', 0)} | queued={data['queue_proxy']} | displayed={len(data.get('vehicles', []))}{suffix}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("trace", type=Path); ap.add_argument("--roadnet", type=Path, default=Path("data/xiong_an_20/roadnet.json")); ap.add_argument("--topology", type=Path, default=Path("data/xiong_an_20/topology.json")); a = ap.parse_args()
    root = tk.Tk(); LiveMonitor(root, a.trace, a.roadnet, a.topology); root.mainloop()


if __name__ == "__main__": main()
