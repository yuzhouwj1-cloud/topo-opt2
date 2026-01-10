"""Visualization utilities."""

from typing import Dict

import matplotlib.pyplot as plt
import networkx as nx

from topology import Topology


def visualize_topology(topology: Topology, path: str | None = None) -> None:
    graph = nx.Graph()
    graph.add_edges_from(topology.edges())

    positions: Dict[int, tuple[float, float]] = nx.spring_layout(graph, seed=42)
    nx.draw_networkx(graph, positions, with_labels=True, node_size=400)

    if path:
        plt.savefig(path)
    else:
        plt.show()
