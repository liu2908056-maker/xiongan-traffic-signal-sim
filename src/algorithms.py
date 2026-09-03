"""Common algorithm adapter contract used by the CityFlow platform."""
from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np


class SignalAlgorithm(ABC):
    name: str
    @abstractmethod
    def choose(self, states: np.ndarray) -> np.ndarray: """Return one 0..7 phase action per controlled intersection."""


class FixedTimeAlgorithm(SignalAlgorithm):
    name = "fixed_time"
    def __init__(self, count: int, phase_hold_decisions: int = 3, phase_offset: int = 0): self.count = count; self.step = 0; self.phase_hold_decisions = phase_hold_decisions; self.phase_offset = phase_offset
    def choose(self, states: np.ndarray) -> np.ndarray:
        # The roadnet has eight controllable green phases (plus clearance at index 0).
        # Cycle all eight phases so the baseline cannot starve half of the movements.
        action = np.full(self.count, (self.phase_offset + self.step // self.phase_hold_decisions) % 8, dtype=np.int64); self.step += 1; return action


class MaxPressureAlgorithm(SignalAlgorithm):
    name = "max_pressure"
    # collect_state order is [WL, WT, WR, EL, ET, ER, NL, NT, NR, SL, ST, SR].
    ACTION_LANES = ((1, 4), (7, 10), (0, 3), (6, 9), (0, 1), (3, 4), (9, 10), (6, 7))
    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :12]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        return score.argmax(axis=1).astype(np.int64)


class ActuatedPressureAlgorithm(SignalAlgorithm):
    """Pressure control with a green hold to avoid 10-second phase chatter."""
    name = "actuated_pressure"
    ACTION_LANES = MaxPressureAlgorithm.ACTION_LANES

    def __init__(self, count: int, min_green_decisions: int = 2, max_green_decisions: int = 6, switch_ratio: float = 1.10):
        self.current = np.zeros(count, dtype=np.int64)
        self.age = np.zeros(count, dtype=np.int64)
        self.min_green = min_green_decisions; self.max_green = max_green_decisions; self.switch_ratio = switch_ratio

    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :12]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        best = score.argmax(axis=1).astype(np.int64); current_score = score[np.arange(len(states)), self.current]; best_score = score[np.arange(len(states)), best]
        can_switch = (self.age >= self.min_green) & ((best_score > current_score * self.switch_ratio) | (self.age >= self.max_green))
        actions = np.where(can_switch, best, self.current)
        self.age = np.where(actions == self.current, self.age + 1, 0); self.current = actions
        return actions


class TransytStyleAlgorithm(SignalAlgorithm):
    """Deterministic open-source reimplementation of TRANSYT principles."""
    name = "transyt_style"
    ACTION_LANES = MaxPressureAlgorithm.ACTION_LANES
    def __init__(self, count: int, grid_positions=None, demand_alpha: float = 0.35, instant_weight: float = 0.35, cycle_decisions: int = 9):
        if int(cycle_decisions) < 8: raise ValueError("TRANSYT cycle must be at least 8 decisions for eight phases")
        self.count = count; self.positions = grid_positions or [[i % 5, i // 5] for i in range(count)]
        self.decision_count = 0; self.cycle = int(cycle_decisions)
        self.demand_alpha = float(demand_alpha); self.instant_weight = float(instant_weight); self.demand_ema = None
        self.durations = np.full((count, 8), 4, dtype=np.int64)
        self.offsets = np.asarray([int((p[0] + 2 * p[1]) * 2) % self.cycle for p in self.positions], dtype=np.int64)
    def _plan(self, demand: np.ndarray) -> None:
        scores = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1) + 1.0
        shares = scores / scores.sum(axis=1, keepdims=True)
        durations = np.clip(np.rint(shares * self.cycle).astype(np.int64), 1, max(2, self.cycle // 2))
        for row in range(self.count):
            while durations[row].sum() > self.cycle:
                idx = int(np.argmax(durations[row] - 1)); durations[row, idx] -= 1
            while durations[row].sum() < self.cycle:
                durations[row, int(np.argmax(scores[row]))] += 1
        self.durations = durations
    def choose(self, states: np.ndarray) -> np.ndarray:
        current_demand = states[:, :12]
        if self.demand_ema is None: self.demand_ema = current_demand.astype(np.float32, copy=True)
        else: self.demand_ema = self.demand_alpha * current_demand + (1.0 - self.demand_alpha) * self.demand_ema
        if self.decision_count == 0 or self.decision_count % 30 == 0:
            planning_demand = (1.0 - self.instant_weight) * self.demand_ema + self.instant_weight * current_demand
            self._plan(planning_demand)
        actions = np.empty(self.count, dtype=np.int64)
        for row in range(self.count):
            slot = int((self.decision_count + self.offsets[row]) % self.cycle); phase = 0
            for duration in self.durations[row]:
                if slot < int(duration): break
                slot -= int(duration); phase = (phase + 1) % 8
            actions[row] = phase
        self.decision_count += 1; return actions


class TransytFrapCoordinator(SignalAlgorithm):
    """Hierarchical coordination: TRANSYT progression prior plus FRAP overrides.

    TRANSYT owns the nominal common cycle, split and offset. The frozen
    UGAT+FRAP controller can override that proposal only where the immediate
    lane-pressure gain is material, preventing independent controllers from
    issuing conflicting commands to the same signal.
    """
    name = "ugat_frap_transyt"
    ACTION_LANES = MaxPressureAlgorithm.ACTION_LANES

    def __init__(self, transyt: TransytStyleAlgorithm, frap: SignalAlgorithm,
                 min_green_decisions: int = 1, override_ratio: float = 1.05,
                 overload_ratio: float = 0.95, minimum_gain: float = 1.0):
        self.transyt = transyt; self.frap = frap; self.count = transyt.count; self.name = getattr(self, "name", "ugat_frap_transyt")
        self.min_green = min_green_decisions; self.override_ratio = override_ratio
        self.overload_ratio = overload_ratio; self.minimum_gain = minimum_gain
        self.current = np.zeros(self.count, dtype=np.int64); self.age = np.zeros(self.count, dtype=np.int64)
        self.decisions = 0; self.overrides = 0; self.agreements = 0

    def choose(self, states: np.ndarray) -> np.ndarray:
        transyt_actions = self.transyt.choose(states)
        frap_actions = self.frap.choose(states)
        demand = states[:, :12]
        pressure = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        row = np.arange(self.count); base = pressure[row, transyt_actions]; proposal = pressure[row, frap_actions]
        overloaded = base < np.maximum(1.0, pressure.mean(axis=1) * self.overload_ratio)
        valuable_override = proposal >= np.maximum(base * self.override_ratio, base + self.minimum_gain)
        can_switch = self.age >= self.min_green
        use_frap = (frap_actions != transyt_actions) & can_switch & overloaded & valuable_override
        actions = np.where(use_frap, frap_actions, transyt_actions).astype(np.int64)
        self.overrides += int(use_frap.sum()); self.agreements += int((frap_actions == transyt_actions).sum()); self.decisions += self.count
        self.age = np.where(actions == self.current, self.age + 1, 0); self.current = actions
        return actions

    def coordination_metrics(self) -> dict[str, float | int]:
        return {
            "coordination_decisions": self.decisions,
            "frap_override_count": self.overrides,
            "frap_override_rate": round(self.overrides / max(self.decisions, 1), 6),
            "transyt_frap_agreement_rate": round(self.agreements / max(self.decisions, 1), 6),
            "coordination_override_ratio": self.override_ratio,
            "coordination_overload_ratio": self.overload_ratio,
            "coordination_minimum_gain": self.minimum_gain,
        }
