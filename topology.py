"""Topology representation and builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import random
from typing import Dict, Iterable, List, Set, Tuple

from topo_config import A_GROUP_SIZE, B_GROUP_SIZE, PORTS_PER_CHIP

Edge = Tuple[int, int]


@dataclass
class Topology:
    """Undirected topology with port constraints."""

    adjacency: Dict[int, Set[int]] = field(default_factory=dict)

    def add_edge(self, node_a: int, node_b: int) -> None:
        if node_a == node_b:
            raise ValueError("Self-loops are not allowed")
        self.adjacency.setdefault(node_a, set()).add(node_b)
        self.adjacency.setdefault(node_b, set()).add(node_a)

    def remove_edge(self, node_a: int, node_b: int) -> None:
        self.adjacency.get(node_a, set()).discard(node_b)
        self.adjacency.get(node_b, set()).discard(node_a)

    def neighbors(self, node: int) -> Set[int]:
        return self.adjacency.get(node, set())

    def nodes(self) -> List[int]:
        return list(self.adjacency.keys())

    def edges(self) -> List[Edge]:
        seen = set()
        result = []
        for node, neighbors in self.adjacency.items():
            for neighbor in neighbors:
                edge = tuple(sorted((node, neighbor)))
                if edge not in seen:
                    seen.add(edge)
                    result.append(edge)
        return result

    def degree(self, node: int) -> int:
        return len(self.adjacency.get(node, set()))

    def to_json(self) -> str:
        return json.dumps({"edges": self.edges()}, indent=2)


def build_initial_topology(
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    ports_per_chip: int = PORTS_PER_CHIP,
    seed: int | None = None,
) -> Topology:
    """Create a bipartite topology between group A and group B."""
    rng = random.Random(seed)
    topology = Topology()
    sources = list(range(a_size))
    destinations = list(range(a_size, a_size + b_size))

    source_slots = [node for node in sources for _ in range(ports_per_chip)]
    dest_slots = [node for node in destinations for _ in range(ports_per_chip)]

    rng.shuffle(source_slots)
    rng.shuffle(dest_slots)

    pairs = zip(source_slots, dest_slots, strict=False)
    for src, dst in pairs:
        if dst in topology.neighbors(src):
            continue
        topology.add_edge(src, dst)

    return topology


def available_nodes(topology: Topology, nodes: Iterable[int], limit: int) -> List[int]:
    return [node for node in nodes if topology.degree(node) < limit]


def random_rewire(
    topology: Topology,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    ports_per_chip: int = PORTS_PER_CHIP,
    seed: int | None = None,
) -> Topology:
    """Randomly rewire a single edge while respecting port limits."""
    rng = random.Random(seed)
    edges = topology.edges()
    if not edges:
        return topology

    edge_to_remove = rng.choice(edges)
    topology.remove_edge(*edge_to_remove)

    sources = list(range(a_size))
    destinations = list(range(a_size, a_size + b_size))

    available_sources = available_nodes(topology, sources, ports_per_chip)
    available_destinations = available_nodes(topology, destinations, ports_per_chip)

    if not available_sources or not available_destinations:
        topology.add_edge(*edge_to_remove)
        return topology

    for _ in range(10):
        src = rng.choice(available_sources)
        dst = rng.choice(available_destinations)
        if dst not in topology.neighbors(src):
            topology.add_edge(src, dst)
            return topology

    topology.add_edge(*edge_to_remove)
    return topology
