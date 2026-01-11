"""Plot optimization history."""

from __future__ import annotations

import importlib.util
import os
from typing import Iterable

from simulate import SimulationResult


def plot_history(history: Iterable[SimulationResult], path: str) -> str:
    if importlib.util.find_spec("matplotlib") is None:
        return path

    import matplotlib.pyplot as plt

    times = [item.communication_time for item in history]
    if not times:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig, ax = plt.subplots()
    ax.plot(range(1, len(times) + 1), times, marker="o", markersize=2, linewidth=1)
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Communication Time")
    ax.set_title("Optimization History")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
