"""Simulation utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random
from typing import Dict, Iterable, List, Optional, Tuple

from topo_config import (
    A_GROUP_SIZE,
    B_GROUP_SIZE,
    EXTRA_HOPS,
    MAX_SHORTEST_PATHS,
    RELAY_IMPROVEMENT_THRESHOLD,
    RELAY_SELECTION_MODE,
    RELAY_SELECTION_SEED,
    ROUTING_ITERATIONS,
    ROUTING_STRATEGY,
)
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


def _min_path_cost(
    topology: Topology,
    start: int,
    goal: int,
    edge_loads: Dict[Edge, float],
    max_paths: int,
) -> Optional[float]:
    paths = _all_shortest_paths(topology, start, goal, max_paths)
    if not paths:
        return None
    return min(_path_cost(path, edge_loads) for path in paths)


def _enumerate_paths(
    topology: Topology,
    demand: TrafficDemand,
    routing_strategy: str,
) -> List[List[int]]:
    if routing_strategy in {
        "shortest_multipath",
        "adaptive_multipath",
        "adaptive_selective_relay_b",
    }:
        return _all_shortest_paths(
            topology,
            demand.source,
            demand.destination,
            MAX_SHORTEST_PATHS,
        )
    if routing_strategy in {"bounded_multipath", "adaptive_bounded_multipath"}:
        return _bounded_shortest_paths(
            topology,
            demand.source,
            demand.destination,
            MAX_SHORTEST_PATHS,
            EXTRA_HOPS,
        )
    return []


def _all_pairs_shortest_distances(topology: Topology, node_count: int) -> List[List[int]]:
    distances = [[-1 for _ in range(node_count)] for _ in range(node_count)]
    for src in range(node_count):
        distances[src][src] = 0
        queue: deque[int] = deque([src])
        while queue:
            node = queue.popleft()
            for neighbor in topology.neighbors(node):
                if distances[src][neighbor] != -1:
                    continue
                distances[src][neighbor] = distances[src][node] + 1
                queue.append(neighbor)
    return distances


def _select_relay_candidate(
    topology: Topology,
    src: int,
    targets: List[TrafficDemand],
    distances: List[List[int]],
    edge_loads_seed: Dict[Edge, float],
    relay_selection_mode: str,
) -> Optional[int]:
    candidates = [demand.destination for demand in targets]
    rng = random.Random(RELAY_SELECTION_SEED + src)
    best_cost = None
    best_candidates: List[int] = []
    for relay in candidates:
        if relay_selection_mode == "load":
            cost_src = _min_path_cost(
                topology,
                src,
                relay,
                edge_loads_seed,
                MAX_SHORTEST_PATHS,
            )
            if cost_src is None:
                continue
        else:
            cost_src = distances[src][relay]
            if cost_src < 0:
                continue
        total_cost = cost_src
        for demand in targets:
            if demand.destination == relay:
                continue
            if relay_selection_mode == "load":
                cost_relay = _min_path_cost(
                    topology,
                    relay,
                    demand.destination,
                    edge_loads_seed,
                    MAX_SHORTEST_PATHS,
                )
                if cost_relay is None:
                    total_cost = None
                    break
            else:
                cost_relay = distances[relay][demand.destination]
                if cost_relay < 0:
                    total_cost = None
                    break
            total_cost += cost_relay
        if total_cost is None:
            continue
        if best_cost is None or total_cost < best_cost:
            best_cost = total_cost
            best_candidates = [relay]
        elif total_cost == best_cost:
            best_candidates.append(relay)
    if not best_candidates:
        return None
    return rng.choice(best_candidates)


def _selective_relay_b_traffic(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads_seed: Dict[Edge, float],
) -> List[TrafficDemand]:
    """Route some A->B demands via a single relay in group B when beneficial.

    Relay selection only matters when a source has multiple targets (e.g., MoE traffic).
    """
    node_count = A_GROUP_SIZE + B_GROUP_SIZE
    distances = _all_pairs_shortest_distances(topology, node_count)
    grouped: Dict[int, List[TrafficDemand]] = {}
    passthrough: List[TrafficDemand] = []
    b_start = A_GROUP_SIZE
    b_end = A_GROUP_SIZE + B_GROUP_SIZE
    for demand in traffic:
        if 0 <= demand.source < A_GROUP_SIZE and b_start <= demand.destination < b_end:
            grouped.setdefault(demand.source, []).append(demand)
        else:
            passthrough.append(demand)

    result: List[TrafficDemand] = list(passthrough)
    for src, targets in grouped.items():
        relay = _select_relay_candidate(
            topology,
            src,
            targets,
            distances,
            edge_loads_seed,
            RELAY_SELECTION_MODE,
        )
        if relay is None:
            result.extend(targets)
            continue
        forwarded: List[TrafficDemand] = []
        direct: List[TrafficDemand] = []
        cost_src_relay = _min_path_cost(
            topology,
            src,
            relay,
            edge_loads_seed,
            MAX_SHORTEST_PATHS,
        )
        for demand in targets:
            if demand.destination == relay:
                continue
            cost_direct = _min_path_cost(
                topology,
                demand.source,
                demand.destination,
                edge_loads_seed,
                MAX_SHORTEST_PATHS,
            )
            cost_relay_dst = _min_path_cost(
                topology,
                relay,
                demand.destination,
                edge_loads_seed,
                MAX_SHORTEST_PATHS,
            )
            cost_via = None
            if cost_src_relay is not None and cost_relay_dst is not None:
                cost_via = cost_src_relay + cost_relay_dst
            if cost_direct is None and cost_via is None:
                continue
            if cost_direct is None:
                forwarded.append(demand)
                continue
            if cost_via is None:
                direct.append(demand)
                continue
            if cost_via <= cost_direct * (1.0 - RELAY_IMPROVEMENT_THRESHOLD):
                forwarded.append(demand)
            else:
                direct.append(demand)

        if forwarded:
            result.append(TrafficDemand(src, relay, targets[0].volume))
            result.extend(TrafficDemand(relay, d.destination, d.volume) for d in forwarded)
            result.extend(direct)
        else:
            result.extend(targets)
    return result


def _route_loads(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads_seed: Dict[Edge, float],
    routing_strategy: str,
) -> tuple[Dict[Edge, float], int]:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    if routing_strategy == "adaptive_selective_relay_b":
        traffic = _selective_relay_b_traffic(topology, traffic, edge_loads_seed)

    for demand in traffic:
        if routing_strategy in {
            "shortest_multipath",
            "adaptive_multipath",
            "adaptive_selective_relay_b",
            "bounded_multipath",
            "adaptive_bounded_multipath",
        }:
            paths = _enumerate_paths(topology, demand, routing_strategy)
            if not paths:
                disconnected += 1
                continue
            if routing_strategy in {
                "adaptive_multipath",
                "adaptive_selective_relay_b",
                "adaptive_bounded_multipath",
            }:
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


def simulate(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    routing_strategy: str = ROUTING_STRATEGY,
) -> SimulationResult:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    if routing_strategy in {
        "adaptive_multipath",
        "adaptive_selective_relay_b",
        "adaptive_bounded_multipath",
    }:
        for _ in range(max(1, ROUTING_ITERATIONS)):
            edge_loads, disconnected = _route_loads(
                topology,
                traffic,
                edge_loads,
                routing_strategy,
            )
    else:
        edge_loads, disconnected = _route_loads(
            topology,
            traffic,
            edge_loads,
            routing_strategy,
        )

    max_edge_load = max(edge_loads.values(), default=0.0)
    communication_time = max_edge_load
    return SimulationResult(
        communication_time=communication_time,
        max_edge_load=max_edge_load,
        disconnected_flows=disconnected,
        edge_loads=edge_loads,
    )
