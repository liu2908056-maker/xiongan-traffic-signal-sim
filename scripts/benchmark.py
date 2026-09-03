#!/usr/bin/env python3
"""功能二-任务三 性能统计脚本。

批量运行基线（fixed / max_pressure）与自研算法（ugat_frap 等），
并从 outputs/metrics.csv 汇总生成性能对比。

在 Docker 容器内运行（需要 CityFlow 引擎）：
    python scripts/benchmark.py --algorithms fixed,max_pressure,ugat_frap --periods morning,midday --steps 7500 --threads 4

只汇总已有结果（不重跑）：
    python scripts/benchmark.py --summarize-only
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS_CSV = ROOT / "outputs" / "metrics.csv"

# 指标列（与 src/run_cityflow.py 输出一致）
KEY_METRICS = [
    "average_travel_time_s",   # 平均旅行时间（越低越好）
    "estimated_delay_s",       # 平均延误（越低越好）
    "throughput_est",          # 吞吐量（越高越好）
    "final_queue_proxy",       # 最终排队（越低越好）
    "steps_per_second",        # 运行速度 / 性能（越高越好）
    "wall_seconds",            # 单次运行墙钟时间
]


def run_one(algorithm: str, period: str, steps: int, threads: int, flow_file: str | None = None) -> None:
    cmd = [
        sys.executable, str(ROOT / "src" / "run_cityflow.py"),
        "--algorithm", algorithm,
        "--period", period,
        "--steps", str(steps),
        "--threads", str(threads),
    ]
    if flow_file:
        cmd += ["--flow-file", flow_file]
    print(f"[run] {algorithm} @ {period} ({steps} steps)")
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def summarize() -> None:
    if not METRICS_CSV.exists():
        print(f"未找到 {METRICS_CSV}，请先运行 benchmark 或 run_cityflow.py")
        return
    with METRICS_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("metrics.csv 为空")
        return
    print("\n===== 性能对比 =====")
    header = ["algorithm", "period", "steps", *KEY_METRICS]
    print("\t".join(header))
    for r in rows:
        print("\t".join(str(r.get(k, "")) for k in header))
    print("\n说明：指标定义见 docs/性能对比表.md；"
          "公平对比需同一场景、同一流量、同一随机种子。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algorithms", default="fixed,max_pressure,ugat_frap")
    ap.add_argument("--periods", default="morning,midday,evening")
    ap.add_argument("--steps", type=int, default=7500)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--flow-file", default=None,
                    help="压力流量，如 flow_midday_pressure30.json")
    ap.add_argument("--summarize-only", action="store_true",
                    help="仅汇总现有 metrics.csv，不重跑")
    args = ap.parse_args()

    if args.summarize_only:
        summarize()
        return

    for algorithm in args.algorithms.split(","):
        for period in args.periods.split(","):
            run_one(algorithm.strip(), period.strip(),
                    args.steps, args.threads, args.flow_file)
    summarize()


if __name__ == "__main__":
    main()
