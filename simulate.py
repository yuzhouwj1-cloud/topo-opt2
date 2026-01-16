"""Simulation utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from topo_config import EXTRA_HOPS, MAX_SHORTEST_PATHS, ROUTING_ITERATIONS, ROUTING_STRATEGY
from traffic import TrafficDemand
from topology import Topology


@dataclass(frozen=True)
class SimulationResult:
    communication_time: float
    max_edge_load: float
    disconnected_flows: int
    edge_loads: Dict[Edge, float]


Edge = Tuple[int, int]


def _shortest_path(topology: Topology, start: int, goal: int) -> Optional[List[int]]:
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


def _bounded_shortest_paths(
    topology: Topology,
    start: int,
    goal: int,
    max_paths: int,
    extra_hops: int,
) -> List[List[int]]:
    if start == goal:
        return [[start]]
    queue: deque[int] = deque([start])
    dist_start: Dict[int, int] = {start: 0}
    while queue:
        node = queue.popleft()
        for neighbor in topology.neighbors(node):
            if neighbor not in dist_start:
                dist_start[neighbor] = dist_start[node] + 1
                queue.append(neighbor)
    if goal not in dist_start:
        return []

    queue = deque([goal])
    dist_goal: Dict[int, int] = {goal: 0}
    while queue:
        node = queue.popleft()
        for neighbor in topology.neighbors(node):
            if neighbor not in dist_goal:
                dist_goal[neighbor] = dist_goal[node] + 1
                queue.append(neighbor)

    shortest = dist_start[goal]
    max_hops = shortest + extra_hops

    paths: List[List[int]] = []
    stack: List[tuple[int, List[int]]] = [(start, [start])]
    while stack and len(paths) < max_paths:
        node, path = stack.pop()
        if len(path) - 1 > max_hops:
            continue
        if node == goal:
            paths.append(path)
            continue
        for neighbor in topology.neighbors(node):
            if neighbor in path:
                continue
            if neighbor not in dist_goal:
                continue
            if dist_start[node] + 1 + dist_goal[neighbor] > max_hops:
                continue
            stack.append((neighbor, path + [neighbor]))
    return paths


def _path_cost(path: List[int], edge_loads: Dict[Edge, float]) -> float:
    edges = _path_edges(path)
    return sum(edge_loads.get(edge, 0.0) + 1.0 for edge in edges)


def _enumerate_paths(topology: Topology, demand: TrafficDemand) -> List[List[int]]:
    if ROUTING_STRATEGY in {"shortest_multipath", "adaptive_multipath"}:
        return _all_shortest_paths(
            topology,
            demand.source,
            demand.destination,
            MAX_SHORTEST_PATHS,
        )
    if ROUTING_STRATEGY in {"bounded_multipath", "adaptive_bounded_multipath"}:
        return _bounded_shortest_paths(
            topology,
            demand.source,
            demand.destination,
            MAX_SHORTEST_PATHS,
            EXTRA_HOPS,
        )
    return []


def _route_loads(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads_seed: Dict[Edge, float],
) -> tuple[Dict[Edge, float], int]:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    for demand in traffic:
        if ROUTING_STRATEGY in {
            "shortest_multipath",
            "adaptive_multipath",
            "bounded_multipath",
            "adaptive_bounded_multipath",
        }:
            paths = _enumerate_paths(topology, demand)
            if not paths:
                disconnected += 1
                continue
            if ROUTING_STRATEGY in {"adaptive_multipath", "adaptive_bounded_multipath"}:
                costs = [_path_cost(path, edge_loads_seed) for path in paths]
                total_weight = sum(1.0 / cost for cost in costs if cost > 0)
                if total_weight == 0:
                    total_weight = float(len(paths))
                    costs = [1.0 for _ in paths]
                for path, cost in zip(paths, costs):
                    share = demand.volume * (1.0 / cost) / total_weight
                    for edge in _path_edges(path):
                        edge_loads[edge] = edge_loads.get(edge, 0.0) + share
            else:
                volume_share = demand.volume / len(paths)
                for path in paths:
                    for edge in _path_edges(path):
                        edge_loads[edge] = edge_loads.get(edge, 0.0) + volume_share
            continue

        path = _shortest_path(topology, demand.source, demand.destination)
        if path is None:
            disconnected += 1
            continue
        for edge in _path_edges(path):
            edge_loads[edge] = edge_loads.get(edge, 0.0) + demand.volume

    return edge_loads, disconnected


def simulate(topology: Topology, traffic: Iterable[TrafficDemand]) -> SimulationResult:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    if ROUTING_STRATEGY in {"adaptive_multipath", "adaptive_bounded_multipath"}:
        for _ in range(max(1, ROUTING_ITERATIONS)):
            edge_loads, disconnected = _route_loads(topology, traffic, edge_loads)
    else:
        edge_loads, disconnected = _route_loads(topology, traffic, edge_loads)

    max_edge_load = max(edge_loads.values(), default=0.0)
    communication_time = max_edge_load
    return SimulationResult(
        communication_time=communication_time,
        max_edge_load=max_edge_load,
        disconnected_flows=disconnected,
        edge_loads=edge_loads,
    )
