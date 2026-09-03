"""Check that the official CityFlow Python extension is importable."""
from __future__ import annotations
import importlib.util
import json
import sys

def main() -> None:
    spec = importlib.util.find_spec("cityflow")
    if spec is None:
        raise SystemExit("CityFlow is not installed. Install the official source with: python -m pip install 'git+https://github.com/cityflow-project/CityFlow.git'")
    import cityflow
    result = {"module": spec.origin, "version": getattr(cityflow, "__version__", "unknown"), "engine": hasattr(cityflow, "Engine"), "python": sys.version.split()[0]}
    if not result["engine"]:
        raise SystemExit(json.dumps(result))
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
