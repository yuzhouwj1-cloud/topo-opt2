"""Topology representation and builders."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import random
from typing import Dict, Iterable, List, Set, Tuple

from topo_config import A_GROUP_SIZE, ALLOW_INTRA_GROUP, B_GROUP_SIZE, PORTS_PER_CHIP

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
    allow_intra_group: bool = ALLOW_INTRA_GROUP,
    seed: int | None = None,
) -> Topology:
    """Create an initial topology between chips."""
    rng = random.Random(seed)
    topology = Topology()

    if allow_intra_group:
        nodes = list(range(a_size + b_size))
        slots = [node for node in nodes for _ in range(ports_per_chip)]
        rng.shuffle(slots)
        max_attempts = len(slots) * 4
        attempts = 0
        while len(slots) >= 2 and attempts < max_attempts:
            node_a = slots.pop()
            node_b = slots.pop()
            if node_a == node_b:
                slots.extend([node_a, node_b])
                attempts += 1
                continue
            if node_b in topology.neighbors(node_a):
                slots.extend([node_a, node_b])
                attempts += 1
                continue
            topology.add_edge(node_a, node_b)
        fill_attempts = len(nodes) * ports_per_chip * 10
        while fill_attempts > 0:
            available = [node for node in nodes if topology.degree(node) < ports_per_chip]
            if len(available) < 2:
                break
            node_a = rng.choice(available)
            candidates = [
                node
                for node in available
                if node != node_a and node not in topology.neighbors(node_a)
            ]
            if not candidates:
                fill_attempts -= 1
                continue
            node_b = rng.choice(candidates)
            topology.add_edge(node_a, node_b)
        return topology

    sources = list(range(a_size))
    destinations = list(range(a_size, a_size + b_size))

    source_slots = [node for node in sources for _ in range(ports_per_chip)]
    dest_slots = [node for node in destinations for _ in range(ports_per_chip)]

    rng.shuffle(source_slots)
    rng.shuffle(dest_slots)

    max_attempts = len(source_slots) * 4
    attempts = 0
    while source_slots and dest_slots and attempts < max_attempts:
        src = source_slots.pop()
        dst_index = next(
            (idx for idx, dst in enumerate(dest_slots) if dst not in topology.neighbors(src)),
            None,
        )
        if dst_index is None:
            source_slots.insert(0, src)
            attempts += 1
            continue
        dst = dest_slots.pop(dst_index)
        topology.add_edge(src, dst)

    return topology


def available_nodes(topology: Topology, nodes: Iterable[int], limit: int) -> List[int]:
    return [node for node in nodes if topology.degree(node) < limit]


def topology_from_edges(edges: Iterable[Edge], node_count: int) -> Topology:
    topology = Topology()
    for node in range(node_count):
        topology.adjacency.setdefault(node, set())
    for node_a, node_b in edges:
        topology.add_edge(node_a, node_b)
    return topology


def random_rewire(
    topology: Topology,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    ports_per_chip: int = PORTS_PER_CHIP,
    allow_intra_group: bool = ALLOW_INTRA_GROUP,
    seed: int | None = None,
) -> Topology:
    """Randomly rewire a single edge while respecting port limits."""
    rng = random.Random(seed)
    edges = topology.edges()
    if not edges:
        return topology

    edge_to_remove = rng.choice(edges)
    topology.remove_edge(*edge_to_remove)

    if allow_intra_group:
        nodes = list(range(a_size + b_size))
        available_nodes_list = available_nodes(topology, nodes, ports_per_chip)
        if len(available_nodes_list) < 2:
            topology.add_edge(*edge_to_remove)
            return topology
        for _ in range(20):
            src, dst = rng.sample(available_nodes_list, 2)
            if dst not in topology.neighbors(src):
                topology.add_edge(src, dst)
                return topology
    else:
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


def random_swap_edges(
    topology: Topology,
    seed: int | None = None,
) -> Topology:
    """Swap endpoints between two edges to explore larger moves."""
    rng = random.Random(seed)
    edges = topology.edges()
    if len(edges) < 2:
        return topology

    edge_a, edge_b = rng.sample(edges, 2)
    a_src, a_dst = edge_a
    b_src, b_dst = edge_b

    if a_src == b_src or a_dst == b_dst:
        return topology
    if a_src == b_dst or b_src == a_dst:
        return topology

    topology.remove_edge(a_src, a_dst)
    topology.remove_edge(b_src, b_dst)

    if b_dst in topology.neighbors(a_src) or a_dst in topology.neighbors(b_src):
        topology.add_edge(a_src, a_dst)
        topology.add_edge(b_src, b_dst)
        return topology

    topology.add_edge(a_src, b_dst)
    topology.add_edge(b_src, a_dst)
    return topology
