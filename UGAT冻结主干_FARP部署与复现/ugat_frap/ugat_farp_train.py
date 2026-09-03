import argparse, json, random, csv
from pathlib import Path
import numpy as np
import torch
from ugat_farp_model import UGATWithFRAP

def data(path):
    if path:
        d = torch.load(path, map_location="cpu", weights_only=True)
        x, y = d["x"].float(), d["y"].float()
    else:
        g = torch.Generator().manual_seed(20260806)
        x = torch.randn(128, 16, generator=g)
        y = torch.zeros(128, 8); y[:, 0] = 1
    if x.ndim != 2 or x.shape[1] != 16 or y.shape != (x.shape[0], 8):
        raise ValueError("expected x=[N,16] and y=[N,8]")
    return x, y

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["inspect", "test", "train"], default="inspect")
    ap.add_argument("--checkpoint", default="official_ugat_best.pt")
    ap.add_argument("--state", default="farp_resume.pt")
    ap.add_argument("--data", default="")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    torch.manual_seed(20260806); np.random.seed(20260806); random.seed(20260806)
    model = UGATWithFRAP(a.checkpoint)
    trainable, frozen = model.parameter_report()
    print(f"official_ugat_frozen_parameters={frozen}")
    print(f"frap_trainable_parameters={trainable}")
    print("optimizer_parameter_groups=frap_and_fusion_only")
    if a.mode == "inspect": return
    x, y = data(a.data)
    opt = torch.optim.Adam((p for p in model.parameters() if p.requires_grad), lr=1e-3)
    start, best = 0, float("inf")
    if a.resume:
        s = torch.load(a.state, map_location="cpu", weights_only=True)
        model.frap.load_state_dict(s["frap"]); model.fusion.data.copy_(s["fusion"])
        opt.load_state_dict(s["optimizer"]); start = s["epoch"] + 1; best = s["best_loss"]
        print(f"resumed_from_epoch={start}")
    if a.mode == "test":
        with torch.no_grad(): out = model(x); loss = ((out-y)**2).mean().item()
        print(json.dumps({"test_loss": loss, "finite": bool(torch.isfinite(out).all()), "q_shape": list(out.shape)})); return
    metrics_path = Path(a.state).with_name("farp_training_metrics.csv")
    plot_path = Path(a.state).with_name("farp_training_loss.png")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    if not metrics_path.exists():
        with metrics_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["epoch", "loss", "best_loss"])
    for e in range(start, start + a.epochs):
        opt.zero_grad(); out = model(x); loss = ((out-y)**2).mean(); loss.backward(); opt.step()
        best = min(best, loss.item())
        torch.save({"frap": model.frap.state_dict(), "fusion": model.fusion.detach().clone(),
                    "optimizer": opt.state_dict(), "epoch": e, "best_loss": best}, a.state)
        with metrics_path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([e + 1, loss.item(), best])
        try:
            import matplotlib.pyplot as plt
            rows = list(csv.DictReader(metrics_path.open(encoding="utf-8")))
            plt.figure(figsize=(7, 4)); plt.plot([r["epoch"] for r in rows], [r["loss"] for r in rows], label="loss")
            plt.xlabel("epoch"); plt.ylabel("MSE loss"); plt.title("UGAT + FARP training loss"); plt.grid(alpha=.3); plt.legend(); plt.tight_layout(); plt.savefig(plot_path, dpi=160); plt.close()
        except Exception as exc:
            print(f"plot_warning={exc}")
        print(f"epoch={e+1} loss={loss.item():.6f} best_loss={best:.6f} state={a.state}")
if __name__ == "__main__": main()
