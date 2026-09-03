# CityFlow 官方安装与核验

官方源码：<https://github.com/cityflow-project/CityFlow>

CityFlow 是 C++/Python 扩展，建议在 Linux 或官方已有 UGAT 镜像中使用：

```bash
apt-get update && apt-get install -y git cmake build-essential
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/cityflow-project/CityFlow.git"
python src/check_cityflow.py
```

项目 `Dockerfile` 默认从项目内固定提交的官方源码 `third_party/CityFlow` 构建 CityFlow 扩展：

```bash
docker build -t xiong-an-20-platform:cityflow-source .
```

## 核验

```bash
python src/check_cityflow.py
python src/validate_scenario.py
python src/run_cityflow.py --period morning --algorithm ugat_frap --steps 100
```

`check_cityflow.py` 会输出模块路径、版本（若发行包提供）和 `Engine` 构造能力；它不会只检查 Python 包名。
