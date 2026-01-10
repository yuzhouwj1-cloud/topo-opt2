"""Export topology to CSV/JSON."""

import csv
import json
from typing import Iterable, Tuple

from topology import Edge, Topology


def export_edges_csv(edges: Iterable[Edge], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["node_a", "node_b"])
        for node_a, node_b in edges:
            writer.writerow([node_a, node_b])


def export_edges_json(edges: Iterable[Tuple[int, int]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([{"node_a": a, "node_b": b} for a, b in edges], handle, indent=2)


def export_topology(topology: Topology, path: str) -> None:
    if path.endswith(".csv"):
        export_edges_csv(topology.edges(), path)
        return
    if path.endswith(".json"):
        export_edges_json(topology.edges(), path)
        return
    raise ValueError("Unsupported export format; use .csv or .json")
