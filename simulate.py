"""Simulation utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from topo_config import MAX_SHORTEST_PATHS, ROUTING_STRATEGY
from traffic import TrafficDemand
from topology import Topology


@dataclass(frozen=True)
class SimulationResult:
    communication_time: float
    max_edge_load: float
    disconnected_flows: int


Edge = Tuple[int, int]


def _shortest_path(topology: Topology, start: int, goal: int) -> List[int] | None:
    if start == goal:
        return [start]
    visited = {start}
    queue: deque[Tuple[int, List[int]]] = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        for neighbor in topology.neighbors(node):
            if neighbor in visited:
                continue
            if neighbor == goal:
                return path + [neighbor]
            visited.add(neighbor)
            queue.append((neighbor, path + [neighbor]))
    return None


def _path_edges(path: List[int]) -> List[Edge]:
    return [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]


def _all_shortest_paths(
    topology: Topology,
    start: int,
    goal: int,
    max_paths: int,
) -> List[List[int]]:
    if start == goal:
        return [[start]]
    queue: deque[int] = deque([start])
    distance: Dict[int, int] = {start: 0}
    parents: Dict[int, List[int]] = {start: []}
    while queue:
        node = queue.popleft()
        for neighbor in topology.neighbors(node):
            if neighbor not in distance:
                distance[neighbor] = distance[node] + 1
                parents[neighbor] = [node]
                queue.append(neighbor)
            elif distance[neighbor] == distance[node] + 1:
                parents[neighbor].append(node)
    if goal not in distance:
        return []

    paths: List[List[int]] = []
    stack: List[tuple[int, List[int]]] = [(goal, [goal])]
    while stack and len(paths) < max_paths:
        node, path = stack.pop()
        if node == start:
            paths.append(list(reversed(path)))
            continue
        for parent in parents.get(node, []):
            stack.append((parent, path + [parent]))
    return paths


def simulate(topology: Topology, traffic: Iterable[TrafficDemand]) -> SimulationResult:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    for demand in traffic:
        if ROUTING_STRATEGY == "shortest_multipath":
            paths = _all_shortest_paths(
                topology,
                demand.source,
                demand.destination,
                MAX_SHORTEST_PATHS,
            )
            if not paths:
                disconnected += 1
                continue
            volume_share = demand.volume / len(paths)
            for path in paths:
                for edge in _path_edges(path):
                    edge_loads[edge] = edge_loads.get(edge, 0.0) + volume_share
        else:
            path = _shortest_path(topology, demand.source, demand.destination)
            if path is None:
                disconnected += 1
                continue
            for edge in _path_edges(path):
                edge_loads[edge] = edge_loads.get(edge, 0.0) + demand.volume

    max_edge_load = max(edge_loads.values(), default=0.0)
    communication_time = max_edge_load
    return SimulationResult(
        communication_time=communication_time,
        max_edge_load=max_edge_load,
        disconnected_flows=disconnected,
    )
