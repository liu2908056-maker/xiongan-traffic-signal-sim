# 功能二任务一场景构建与数据导入验收记录

## 交付内容

本包提供雄安典型区域 20 个受控路口的 CityFlow 联动场景。`manifest.json` 列出 J01-J20 的来源工作簿和三时段统计，`topology.json` 提供路口拓扑与地图坐标，`roadnet.json` 提供道路、车道、roadLinks 与统一八相位信号灯，`source_signal_plans.json` 保留原始配时方案。

流量数据为早高峰、平峰、晚高峰，另含平峰压力 10、20、30、120 的四档扰动。`src/build_xiong_an_20.py` 是从 Excel 导入/转换的来源脚本；提交包包含其已转换后的数据，以便无需原始 Excel 也能复现。

## 合法性检查

执行命令：

```powershell
python .\src\validate_scenario.py
```

结果：通过。共 20 个受控路口、294 条道路；每个路口均有 8 个可控相位和 1 个清空相位。路由均引用存在道路，相邻道路转换均存在于目标路口 roadLinks。早/平/晚高峰分别为 77,749、54,864、87,051 辆；路口、进口方向和车辆总数均与 20/20 份 Excel 审计记录一致。

## CityFlow 运行复现

官方源码仓库：<https://github.com/cityflow-project/CityFlow>。本包的 `third_party/CityFlow` 固定于提交 `81ee0f47659ca66177a71f81676691c58ee89184`，包含 `pybind11` 与 `rapidjson` 子模块源码。Dockerfile 从该本地源码编译 Python 扩展，不采用系统已有二进制。

2026-08-29 使用 CityFlow 0.1、Python 3.10.6 Docker 运行：

```powershell
docker run --rm -v "${PWD}:/app" -w /app --entrypoint python xiong-an-task1:cityflow-local src/run_cityflow.py --period morning --algorithm max_pressure --steps 7500 --decision-interval 10 --threads 1 --out-dir outputs/cityflow_morning_7500
```

结果文件：`outputs/cityflow_morning_7500/metrics.csv`。运行 7,500 秒，全部 77,749 辆需求已调度，完成估计 77,720 辆，完成率 0.999627，最终活跃车辆 29。该结果证明完整 20 路口联动场景可被原生 CityFlow 加载和运行。

压力扰动复验：`flow_midday_pressure30.json` 在相同 CityFlow 环境运行 120 步，71,323 辆总需求中已调度 1,124 辆、完成估计 1,122 辆，说明压力流量文件可被引擎读取并执行。

Dockerfile 已于 2026-08-29 从零构建验证成功：以 `python:3.10-slim` 为基础，编译本包 `third_party/CityFlow` 后，构建阶段通过场景校验和 `cityflow.Engine` 导入检查；新镜像的 120 步早高峰 smoke test 也已通过。提交包同时提供该已验证镜像的离线归档及 SHA-256 校验值，评审环境不需要访问 Docker Hub。
