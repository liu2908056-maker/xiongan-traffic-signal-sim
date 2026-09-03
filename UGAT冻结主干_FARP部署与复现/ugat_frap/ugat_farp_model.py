"""Frozen official UGAT backbone with a trainable FRAP phase-competition head.

The project historically names this algorithm FRAP; the delivery folder uses
FARP because that is the requested name. The official UGAT state_dict is never
updated. FRAP receives a compact [phase_index, eight lane demands] view derived
from the 16-value UGAT observation.
"""
import torch
from torch import nn
import torch.nn.functional as F


class OfficialUGAT(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        self.dense_1 = nn.Linear(16, 20)
        self.dense_2 = nn.Linear(20, 20)
        self.dense_3 = nn.Linear(20, 8)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if set(state) != set(self.state_dict()):
            raise RuntimeError("official checkpoint keys do not match DQN(16,20,20,8)")
        self.load_state_dict(state)
        for p in self.parameters():
            p.requires_grad = False

    def forward(self, x, train=True):
        with torch.no_grad():
            return self.dense_3(F.relu(self.dense_2(F.relu(self.dense_1(x)))))


class FRAPHead(nn.Module):
    """Compact FRAP phase-competition network for eight actions."""
    def __init__(self, num_actions=8, demand_shape=1):
        super().__init__()
        self.num_actions = num_actions
        self.demand_shape = demand_shape
        self.phase_pairs = [(i, (i + 1) % num_actions) for i in range(num_actions)]
        self.comp_mask = torch.ones(num_actions, num_actions, dtype=torch.long)
        self.p = nn.Embedding(2, 4)
        self.d = nn.Linear(demand_shape, 4)
        self.lane_embedding = nn.Linear(8, 16)
        self.lane_conv = nn.Conv2d(32, 20, 1)
        self.relation_embedding = nn.Embedding(2, 4)
        self.relation_conv = nn.Conv2d(4, 20, 1)
        self.hidden_layer = nn.Conv2d(20, 20, 1)
        self.before_merge = nn.Conv2d(20, 1, 1)

    def forward(self, compact):
        if compact.ndim != 2 or compact.shape[1] != 9:
            raise ValueError("FRAP input must have shape [batch, 9]: phase + 8 lane demands")
        phase = compact[:, :1].long().remainder(8)
        lanes = compact[:, 1:].float().reshape(-1, 8, 1)
        phase_onehot = F.one_hot(phase[:, 0], 8).long()
        phase_embed = torch.sigmoid(self.p(phase_onehot))
        demand = torch.sigmoid(self.d(lanes))
        lane = F.relu(self.lane_embedding(torch.cat([phase_embed, demand], -1)))
        pairs = torch.stack([lane[:, a] + lane[:, b] for a, b in self.phase_pairs], 1)
        rotated = torch.stack([torch.cat([pairs[:, i], pairs[:, j]], -1)
                               for i in range(8) for j in range(8) if i != j], 1)
        rotated = rotated.reshape(-1, 8, 7, 32).permute(0, 3, 1, 2)
        rotated = F.relu(self.lane_conv(rotated))
        relation_pairs = torch.stack([self.comp_mask[i, j]
                                      for i in range(8) for j in range(8) if i != j])
        relation_pairs = relation_pairs.reshape(8, 7)
        rel_embed = self.relation_embedding(relation_pairs).permute(2, 0, 1)
        rel = F.relu(self.relation_conv(rel_embed.unsqueeze(0).expand(compact.size(0), -1, -1, -1)))
        merged = F.relu(self.hidden_layer(rotated) * rel)
        scores = self.before_merge(merged).reshape(-1, 8, 7).sum(2)
        return scores


class UGATWithFRAP(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        self.ugat = OfficialUGAT(checkpoint)
        self.frap = FRAPHead()
        self.fusion = nn.Parameter(torch.tensor(0.0))

    @staticmethod
    def compact_observation(x):
        # CityFlow 1x1 DQN feature order: 8 lane counts followed by 8 phase one-hot values.
        phase_index = torch.argmax(x[:, 8:16], dim=1, keepdim=True).float()
        return torch.cat([phase_index, x[:, :8]], dim=1)

    def forward(self, x, train=True):
        ugat_q = self.ugat(x)
        frap_q = self.frap(self.compact_observation(x))
        return ugat_q + torch.sigmoid(self.fusion) * frap_q

    def parameter_report(self):
        frozen = sum(p.numel() for p in self.ugat.parameters())
        trainable = sum(p.numel() for p in self.frap.parameters()) + self.fusion.numel()
        return trainable, frozen
