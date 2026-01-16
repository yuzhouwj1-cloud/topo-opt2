"""Traffic heatmap visualization."""

from __future__ import annotations

from typing import Iterable, List

import matplotlib.pyplot as plt

from traffic import TrafficDemand, traffic_matrix
from topo_config import A_GROUP_SIZE, B_GROUP_SIZE, N


def plot_traffic_heatmap(
    traffic: Iterable[TrafficDemand],
    output_path: str,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    node_count: int = N,
) -> str:
    """Plot a src x dest heatmap of traffic demands (group A then group B)."""
    matrix: List[List[int]] = traffic_matrix(
        a_size=a_size,
        b_size=b_size,
        node_count=node_count,
        traffic=traffic,
    )

    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(matrix, cmap="viridis", interpolation="nearest", aspect="auto")
    ax.set_xlabel("Destination")
    ax.set_ylabel("Source")
    ax.set_title("Traffic Heatmap (A->B)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
