# 功能二-任务三：平台部署与性能优化

> 挑战杯「揭榜挂帅」XH-202613 · 赛道 B「经典交通管控算法的场景适配与优化」
> 面向雄安新区「城市大脑」的车路云一体化协同管控算法与仿真平台
> 本仓库内容：功能二-任务三（F2-T3）「平台部署与性能优化」
> 负责人：刘一鸣

---

## 一、项目简介

本仓库基于 [CityFlow](https://github.com/cityflow-project/CityFlow) 交通仿真引擎，构建了面向雄安新区 20 路口场景的交通信号管控仿真平台，并集成 UGAT（图注意力信号控制）+ FRAP（相位竞争学习）协同优化算法，提供 Docker 化部署方案与完整的可复现实验记录。

本仓库聚焦于**平台部署与性能优化**任务，交付内容包括：

- 基于 CityFlow 的雄安 20 路口仿真场景构建与校验
- Docker 化部署（源码构建 / 离线镜像两种方式）
- 干净环境下的完整复现验证（环境、构建、运行、指标全链路）
- 第三方组件与数据来源的许可证合规说明

## 二、环境要求

| 项目 | 版本 / 说明 |
|---|---|
| 操作系统 | Linux x86_64（推荐 Ubuntu 22.04），或 WSL2 + Ubuntu 22.04 |
| Docker | 已在 Docker 29.7.2（x86_64）下验证 |
| Python | 3.10（Docker 镜像内置） |
| 仿真引擎 | CityFlow，固定 commit `81ee0f47659ca66177a71f81676691c58ee89184` |
| 架构 | linux/amd64 |

## 三、快速开始

### 1. 构建镜像（基线版，自包含、已复现验证）

```bash
docker build -f Dockerfile.cityflow_baseline -t xiong-an-20-platform:final .
```

### 2. 运行仿真

```bash
docker run --rm -v "$PWD/outputs:/app/outputs" xiong-an-20-platform:final \
  --period morning --algorithm max_pressure --steps 7500 --threads 4
```

运行结束后，结果输出至 `outputs/` 目录。

> 说明：仓库还提供 `Dockerfile`（UGAT 版），用于依赖外部镜像 `danielda1/ugat`（约 8.47GB）的 UGAT + FRAP 主算法环境；该版本与 fixed 基线的对比评测待后续补跑，详见 `docs/`。

## 四、目录结构

```
.
├── src/                          # 平台源码
│   ├── run_cityflow.py           # 仿真运行入口
│   ├── validate_scenario.py      # 场景校验
│   ├── show_live.py              # 可视化展示
│   ├── build_xiong_an_20.py      # 20 路口场景数据构建（Excel 导入）
│   ├── check_cityflow.py         # CityFlow 环境检查
│   ├── ugat_frap.py              # UGAT + FRAP 算法适配
│   └── algorithms.py             # 基线算法（如 max_pressure）
├── data/xiong_an_20/              # 20 路口路网 / 流量 / 信号配时数据
├── third_party/CityFlow/          # 第三方仿真引擎源码（Docker 构建时本地编译）
├── docker/                        # 离线镜像与校验文件
│   ├── xiong-an-cityflow-submission.tar   # 离线镜像（约 212MB，已排除入库，见 .gitignore）
│   └── SHA256SUMS.txt
├── scripts/                       # 辅助脚本
│   ├── benchmark.py
│   └── run_and_show.ps1
├── docs/                          # 性能对比表、干净环境复现记录、常见错误、运行环境要求
├── UGAT冻结主干_FARP部署与复现/     # UGAT 预训练权重、FRAP 适配与训练脚本、logs/
├── THIRD_PARTY_NOTICES.md         # 第三方组件与数据来源许可证说明
├── Dockerfile                     # UGAT 版
├── Dockerfile.cityflow_baseline   # 基线版（自包含，已复现验证）
└── README.md
```

## 五、复现验证结论

在 WSL2 + Ubuntu 22.04.5 + Docker 29.7.2（x86_64）干净环境下完成完整复现：

- ✅ CityFlow 本地编译成功（`cityflow.cpython-310-x86_64-linux-gnu.so`，Python 3.10）
- ✅ 场景校验 PASS（20 路口 / 294 道路 / 早高峰 77749 车 / 20-20 份 Excel 对齐）
- ✅ 7500 步正式评测跑通（throughput 0.999627，wall 44.7s）
- ✅ 离线镜像 vs 源码构建，100 步输出逐字段一致，验证可复现

详细复现记录与证据（环境 / 构建 / 运行输出 / metrics / docker images）见 `复现材料/` 目录与 `docs/`。

当前复现范围为 max_pressure 基线；UGAT + FRAP 主算法（依赖 `danielda1/ugat` 外部镜像）与 fixed 基线的对比评测待后续补跑。

## 六、许可证说明

- 本仓库自研部分（`src/`、FRAP 适配脚本、Dockerfile、说明文档等）版权归项目团队所有。
- **UGAT**、**FRAP** 上游仓库均无 LICENSE 文件，未声明开源许可证；本项目仅使用其预训练权重 / 算法思想用于学术复现，并在报告中引用相应论文。
- CityFlow（Apache-2.0）、pybind11（BSD-3-Clause）、rapidjson（MIT）、SUMO（EPL-2.0）等第三方组件的完整清单与许可证详情，见 [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md)。
- 预训练权重 `official_ugat_best.pt` 为团队自行训练，经哈希核对确认非官方发布权重，详见 `THIRD_PARTY_NOTICES.md`。

## 七、联系方式

如需了解本任务的其他细节，请联系负责人：刘一鸣。
