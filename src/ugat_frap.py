"""Batched frozen-UGAT plus trainable-FRAP controller for 20 intersections."""
from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
import torch.nn.functional as F

PHASE_PAIRS = ((4, 10), (1, 7), (5, 11), (2, 8), (10, 11), (4, 5), (7, 8), (1, 2))


class FrozenUGAT(nn.Module):
    """The supplied 4x4 UGAT/DQN base. Its parameters must never be optimized."""
    def __init__(self, checkpoint: str | Path):
        super().__init__()
        self.dense_1 = nn.Linear(20, 20); self.dense_2 = nn.Linear(20, 20); self.dense_3 = nn.Linear(20, 8)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if set(state) != set(self.state_dict()): raise RuntimeError("UGAT checkpoint keys do not match the frozen 20->20->20->8 base")
        self.load_state_dict(state)
        for parameter in self.parameters(): parameter.requires_grad_(False)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        with torch.no_grad(): return self.dense_3(F.relu(self.dense_2(F.relu(self.dense_1(state)))))


class FRAPAdapter(nn.Module):
    """Eight-action FRAP relation network; input is [phase one-hot, 12 movements]."""
    def __init__(self):
        super().__init__()
        self.phase_embedding = nn.Embedding(2, 4); self.demand_embedding = nn.Linear(1, 4)
        self.lane_embedding = nn.Linear(8, 16); self.lane_conv = nn.Conv2d(32, 20, 1)
        self.relation_embedding = nn.Embedding(2, 4); self.relation_conv = nn.Conv2d(4, 20, 1)
        self.hidden = nn.Conv2d(20, 20, 1); self.output = nn.Conv2d(20, 1, 1)
        mask = []
        for i, a in enumerate(PHASE_PAIRS): mask.append([int(len(set(a + PHASE_PAIRS[j])) == 3) for j in range(8) if i != j])
        self.register_buffer("conflict_mask", torch.tensor(mask, dtype=torch.long), persistent=False)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        if state.ndim != 2 or state.shape[1] != 20: raise ValueError("expected [batch, 20]")
        phase, lane = state[:, :8], state[:, 8:].reshape(-1, 12, 1)
        active = torch.zeros(state.shape[0], 12, dtype=torch.long, device=state.device)
        for i, (a, b) in enumerate(PHASE_PAIRS):
            is_active = (phase[:, i] > 0.5).long(); active[:, a] = torch.maximum(active[:, a], is_active); active[:, b] = torch.maximum(active[:, b], is_active)
        p = torch.sigmoid(self.phase_embedding(active)); d = torch.sigmoid(self.demand_embedding(lane))
        embedding = F.relu(self.lane_embedding(torch.cat((p, d), dim=-1)))
        pairs = torch.stack([embedding[:, a] + embedding[:, b] for a, b in PHASE_PAIRS], dim=1)
        matchups = torch.stack([torch.cat((pairs[:, i], pairs[:, j]), dim=-1) for i in range(8) for j in range(8) if i != j], dim=1)
        matchups = F.relu(self.lane_conv(matchups.reshape(-1, 8, 7, 32).permute(0, 3, 1, 2)))
        relation = self.relation_embedding(self.conflict_mask).permute(2, 0, 1).unsqueeze(0).expand(state.shape[0], -1, -1, -1)
        relation = F.relu(self.relation_conv(relation))
        return self.output(F.relu(self.hidden(matchups) * relation)).reshape(-1, 8, 7).sum(dim=2)


class UGATFRAPController(nn.Module):
    def __init__(self, checkpoint: str | Path, max_frap_weight: float = 1.0):
        super().__init__(); self.ugat = FrozenUGAT(checkpoint); self.frap = FRAPAdapter()
        self.fusion = nn.Parameter(torch.tensor(0.0)); self.max_frap_weight = float(max_frap_weight)

    def forward(self, cityflow_state: torch.Tensor) -> torch.Tensor:
        # CityFlow collector order: 12 lane demands then 8 active-phase flags.
        ugat_q = self.ugat(cityflow_state); frap_q = self.frap(torch.cat((cityflow_state[:, 12:], cityflow_state[:, :12]), dim=1))
        return ugat_q + self.max_frap_weight * torch.sigmoid(self.fusion) * frap_q

    def assert_frozen(self) -> None:
        if any(p.requires_grad for p in self.ugat.parameters()): raise RuntimeError("UGAT parameters are not frozen")

    def adapter_parameters(self):
        self.assert_frozen(); return [p for p in self.parameters() if p.requires_grad]

    def load_adapter(self, path: str | Path) -> None:
        state = torch.load(path, map_location="cpu", weights_only=True)
        weights = state["frap"]
        # The supplied 4x4 adapter predates the explicit names in this package.
        # Shapes are identical; migrate only the documented module rename.
        rename = {"p.": "phase_embedding.", "d.": "demand_embedding.", "hidden_layer.": "hidden.", "before_merge.": "output."}
        migrated = {next((new + key[len(old):] for old, new in rename.items() if key.startswith(old)), key): value for key, value in weights.items()}
        self.frap.load_state_dict(migrated, strict=True); self.fusion.data.copy_(state["fusion"])
        self.assert_frozen()

    @torch.inference_mode()
    def choose_actions(self, cityflow_state: torch.Tensor) -> torch.Tensor:
        return self(cityflow_state).argmax(dim=1)
