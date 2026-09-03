# 雄安新区 20 路口 UGAT + FRAP 复现说明

本项目沿用 `4x4ugat+frap` 的容器入口、冻结基座和适配器训练方式，但将 CityFlow 场景扩展为 20 个联动控制路口。

CityFlow 官方源码固定在 `third_party/CityFlow`，提交号为 `81ee0f47659ca66177a71f81676691c58ee89184`；Docker 构建阶段会直接编译该源码。

## 静态校验

```powershell
python .\src\validate_scenario.py
```

## 容器内 100 步接口验证

```powershell
docker run --rm -v "${PWD}:/workspace/final" --entrypoint /bin/bash xiong-an-20-platform:final -lc "cd /workspace/final && python src/run_cityflow.py --period morning --algorithm ugat_frap --steps 100 --threads 1"
```

## 7,500 步正式评测

```powershell
docker run --rm -v "${PWD}:/workspace/final" --entrypoint /bin/bash xiong-an-20-platform:final -lc "cd /workspace/final && python src/run_cityflow.py --period morning --algorithm ugat_frap --steps 7500 --threads 4"
```

## 对比算法

将 `--algorithm ugat_frap` 替换为 `max_pressure` 或 `fixed`，指标会追加到 `outputs/metrics.csv`，轨迹写入 `outputs/trace_<algorithm>_morning.json`。

## 一键运行并弹出结果窗口

下面的命令会在 CityFlow 开始后立即自动打开 Windows 原生动态窗口，不需要浏览器。窗口实时显示 4x5 路网、20 个信号相位、各节点排队量和由 CityFlow 返回的车辆道路位置；仿真结束后窗口保留最终状态。首次运行会自动构建镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_and_show.ps1 -Algorithm ugat_frap -Period morning -Steps 7500 -Threads 4
```

比较基线时将 `-Algorithm ugat_frap` 改为 `-Algorithm max_pressure`。动态窗口是 CityFlow 道路位置的实时示意图，不是高精度地图渲染；车辆点位按 CityFlow 的道路和行驶距离显示。

## FRAP 适配器训练

```powershell
docker run --rm -v "${PWD}:/workspace/final" --entrypoint /bin/bash xiong-an-20-platform:final -lc "cd /workspace/final && python src/train_adapter.py --epochs 20"
```

UGAT 检查点始终冻结；训练只更新 FRAP 层和融合标量。训练后重新运行正式评测。
