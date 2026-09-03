# 第三方来源与许可证说明（Third-Party Notices）

本文件声明「功能二-任务三：平台部署与性能优化」代码包中所使用的第三方组件、数据来源及其许可证，用于满足挑战杯 XH-202613 提交材料 **D10「第三方来源与许可证」** 的合规性要求。

## 一、自研与第三方边界

- **自研部分**：`src/` 下的平台入口与算法适配（`run_cityflow.py`、`validate_scenario.py`、`build_xiong_an_20.py`、`check_cityflow.py`、`ugat_frap.py`、`algorithms.py`、`show_live.py`）、`UGAT冻结主干_FARP部署与复现/ugat_frap/` 下的 FARP 适配与训练脚本、`scripts/`、Dockerfile、docker-compose 及全部说明文档。
- **第三方部分**：下表中的仿真引擎、模型、库与数据。

## 二、第三方组件清单

| 组件 | 来源 | 许可证 | 用途 | 修改说明 |
|---|---|---|---|---|
| CityFlow | https://github.com/cityflow-project/CityFlow | **Apache-2.0**（已核实） | 交通仿真引擎 | 源码固定于提交 `81ee0f47659ca66177a71f81676691c58ee89184`；随包本地编译，未修改源码 |
| pybind11 | https://github.com/pybind/pybind11 | **BSD-3-Clause**（已核实） | Python 绑定（CityFlow 子模块） | 未修改 |
| rapidjson | https://github.com/Tencent/rapidjson | **MIT** | JSON 解析（CityFlow 子模块） | 未修改 |
| UGAT | https://github.com/DaRL-LibSignal/UGAT | **未声明开源许可证**（仓库无 LICENSE 文件） | 图注意力信号控制模型，冻结主干用于 FARP 融合 | 仅使用预训练权重 `official_ugat_best.pt`，冻结主干；学术引用 Da et al., CDC 2023 |
| FRAP | https://github.com/gjzheng93/frap-pub | **未声明开源许可证**（仓库无 LICENSE 文件） | 经典交通控制算法 | 作为适配器接入 UGAT 冻结主干；学术引用 Zheng et al., CIKM 2019 |
| danielda1/ugat Docker 镜像 | Docker Hub：`danielda1/ugat` | Hub 无许可证声明 | UGAT 运行环境（Python 3.10.6，内置 CityFlow 与 SUMO） | 第三方预构建镜像，linux/amd64，约 8.47GB，CityFlow 已预编译 |
| SUMO | https://github.com/eclipse-sumo/sumo | **EPL-2.0** | 交通仿真（danielda1/ugat 镜像内置） | 镜像构建时从源码编译 |
| PyTorch (`torch`) | https://pytorch.org | BSD-3-Clause | 深度学习框架 | 见 `requirements.txt` |
| openpyxl | https://openpyxl.readthedocs.io | MIT | Excel 读写 | 见 `requirements.txt` |
| matplotlib | https://matplotlib.org | Matplotlib License (PSF-based) | 图表绘制 | 见 `requirements.txt` |
| python-docx | https://python-docx.readthedocs.io | MIT | Word 文档处理 | 见 `requirements.txt` |

## 三、数据来源

雄安新区 20 路口路网、流量、信号配时数据，来源于**挑战杯 XH-202613 赛题提供的路口数据**（赛题资料-路口数据）。本包通过 `src/build_xiong_an_20.py` 从原始 Excel 导入转换，**未改写原始流量审计结果**（审计证据见 `data/xiong_an_20/excel_audit.json` 与 `manifest.json`）。

## 四、许可证全文索引

- Apache-2.0 全文：`third_party/CityFlow/LICENSE.txt`
- BSD-3-Clause（pybind11）全文：`third_party/CityFlow/extern/pybind11/LICENSE`
- MIT（rapidjson）全文：rapidjson 仓库 LICENSE 文件

## 五、合规提示与待办

许可证查证结论（已通过 GitHub API、README 及 Registry 镜像 config 交叉核对）：

- UGAT、FRAP 仓库均无 LICENSE 文件，未声明开源许可证，代码默认受版权保护（All Rights Reserved）。学术使用分别引用 Da et al., CDC 2023 与 Zheng et al., CIKM 2019。
- `danielda1/ugat:latest` 镜像 Python 版本为 **3.10.6**（非 3.11+），内置 CityFlow（Apache-2.0）与 SUMO（EPL-2.0），Docker Hub 页面无独立许可证或合规声明。
- 需特别说明：UGAT 官方仓库未发布预训练权重。本包 `official_ugat_best.pt`（6058 字节，md5 `1be74408fd37abc7ef6e5daffdc6688b`）经哈希核对，与镜像内置 `-1_0.pt`（md5 `0fe71b6c…`）及 `centralizedGAT` 分支 `260_0.pt`（md5 `c5c416f3…`）均不匹配，确认为团队侧产物（**黄晓凡自行训练**）。

待办：

- [x] 已确认：`official_ugat_best.pt` 为**黄晓凡自行训练**（哈希核对已排除镜像 `-1_0.pt` 与分支 `260_0.pt` 等官方来源）
- [ ] 如竞赛包需再分发 UGAT / FRAP 源码或权重文件，建议书面联系作者（Longchao Da / DaRL Lab, ASU；Guanjie Zheng）确认授权
- [ ] 在报告正文中引用上述两篇论文（BibTeX 见附录）

## 六、参考文献

**UGAT（Da et al., CDC 2023）**

```bibtex
@inproceedings{da2023uncertainty,
  title={Uncertainty-aware Grounded Action Transformation towards Sim-to-Real Transfer for Traffic Signal Control},
  author={Da, Longchao and Mei, Hao and Sharma, Romir and Wei, Hua},
  booktitle={2023 62nd IEEE Conference on Decision and Control (CDC)},
  pages={1124--1129},
  year={2023},
  organization={IEEE}
}
```

**FRAP（Zheng et al., CIKM 2019）**

```bibtex
@inproceedings{zheng2019frap,
  title={Learning phase competition for traffic signal control},
  author={Zheng, Guanjie and Xiong, Yuanhao and Zang, Xinshi and Feng, Jie and Wei, Hua and Zhang, Huichu and Li, Yong and Xu, Kai and Li, Zhenhui},
  booktitle={Proceedings of the 28th ACM International Conference on Information and Knowledge Management},
  pages={1963--1972},
  year={2019}
}
```
