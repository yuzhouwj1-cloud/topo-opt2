"""Visualization utilities."""

from __future__ import annotations

import importlib.util
import os
from typing import Dict, Optional

from topology import Topology


def visualize_topology(topology: Topology, path: Optional[str] = None) -> Optional[str]:
    if importlib.util.find_spec("matplotlib") is None or importlib.util.find_spec("networkx") is None:
        return path

    import matplotlib.pyplot as plt
    import networkx as nx

    graph = nx.Graph()
    graph.add_edges_from(topology.edges())

    positions: Dict[int, tuple[float, float]] = nx.spring_layout(graph, seed=42)
    nx.draw_networkx(graph, positions, with_labels=True, node_size=400)

    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        plt.savefig(path)
    else:
        plt.show()
    plt.close()
    return path
