# UGAT + FARP 指标记录

训练每个 epoch 会更新：

- `logs/farp_training_metrics.csv`
- `logs/farp_training_loss.png`

每次 CityFlow/SUMO 仿真会追加：

- `logs/farp_simulation_metrics.csv`
- `logs/farp_latest_metrics.json`
- `logs/farp_simulation_metrics.png`

CSV 是原始提交数据；PNG 用于报告图表；JSON 用于快速核对最近一次结果。多次运行同一目录会追加到 CSV，不会覆盖历史行。
