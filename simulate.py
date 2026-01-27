"""Simulation utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random
from typing import Dict, Iterable, List, Optional, Tuple

from topo_config import (
    A_GROUP_SIZE,
    B_GROUP_SIZE,
    ASYNC_START_LAMBDA,
    ASYNC_START_SEED,
    EXTRA_HOPS,
    MAX_SHORTEST_PATHS,
    RELAY_IMPROVEMENT_THRESHOLD,
    RELAY_SELECTION_MODE,
    RELAY_SELECTION_SEED,
    ROUTING_ITERATIONS,
    ROUTING_STRATEGY,
    TIMING_MODEL,
)
from traffic import TrafficDemand
from topology import Topology


@dataclass(frozen=True)
class SimulationResult:
    communication_time: float
    max_edge_load: float
    disconnected_flows: int
    edge_loads: Dict[Edge, float]
    request_time_mean: Optional[float] = None
    request_time_variance: Optional[float] = None
    request_completion_times: Optional[Dict[int, float]] = None


Edge = Tuple[int, int]


@dataclass(frozen=True)
class RelayDecision:
    relay: Optional[int]
    targets: List[TrafficDemand]
    forwarded: List[TrafficDemand]
    direct: List[TrafficDemand]


@dataclass
class _Flow:
    flow_id: int
    group_id: int
    request_source: int
    path_edges: List[Edge]
    remaining: float
    start_time: Optional[float]
    depends_on_group: Optional[int]
    completion_time: Optional[float] = None


@dataclass
class _DemandGroup:
    group_id: int
    request_source: int
    destination: int
    pending_flows: int
    completion_time: Optional[float] = None


def _poisson_sample(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k = 0
    product = 1.0
    while product > limit:
        k += 1
        product *= rng.random()
    return k - 1


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


def _pair_completion_cost(
    topology: Topology,
    start: int,
    goal: int,
    edge_loads: Dict[Edge, float],
    routing_strategy: str,
) -> Optional[float]:
    if routing_strategy in {
        "shortest_multipath",
        "adaptive_multipath",
        "adaptive_selective_relay_b",
        "async_optimized",
        "bounded_multipath",
        "adaptive_bounded_multipath",
    }:
        demand = TrafficDemand(start, goal, 1.0)
        paths = _enumerate_paths(topology, demand, routing_strategy)
        if not paths:
            return None
        costs = [_path_cost(path, edge_loads) for path in paths]
        return max(costs)
    path = _shortest_path(topology, start, goal)
    if path is None:
        return None
    return _path_cost(path, edge_loads)


def _path_allocations_for_demand(
    topology: Topology,
    demand: TrafficDemand,
    routing_strategy: str,
    edge_loads_seed: Dict[Edge, float],
) -> Optional[List[tuple[List[Edge], float]]]:
    if routing_strategy in {
        "shortest_multipath",
        "adaptive_multipath",
        "adaptive_selective_relay_b",
        "async_optimized",
        "bounded_multipath",
        "adaptive_bounded_multipath",
    }:
        paths = _enumerate_paths(topology, demand, routing_strategy)
        if not paths:
            return None
        if routing_strategy in {
            "adaptive_multipath",
            "adaptive_selective_relay_b",
            "async_optimized",
            "adaptive_bounded_multipath",
        }:
            costs = [_path_cost(path, edge_loads_seed) for path in paths]
            total_weight = sum(1.0 / cost for cost in costs if cost > 0)
            if total_weight == 0:
                total_weight = float(len(paths))
                costs = [1.0 for _ in paths]
            allocations = []
            for path, cost in zip(paths, costs):
                share = demand.volume * (1.0 / cost) / total_weight
                allocations.append((_path_edges(path), share))
            return allocations
        volume_share = demand.volume / len(paths)
        return [(_path_edges(path), volume_share) for path in paths]
    path = _shortest_path(topology, demand.source, demand.destination)
    if path is None:
        return None
    return [(_path_edges(path), demand.volume)]


def _enumerate_paths(
    topology: Topology,
    demand: TrafficDemand,
    routing_strategy: str,
) -> List[List[int]]:
    if routing_strategy in {
        "shortest_multipath",
        "adaptive_multipath",
        "adaptive_selective_relay_b",
        "async_optimized",
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
    passthrough, decisions = _selective_relay_b_decisions(
        topology,
        traffic,
        edge_loads_seed,
    )
    result: List[TrafficDemand] = list(passthrough)
    for src, decision in decisions.items():
        if decision.relay is None:
            result.extend(decision.targets)
            continue
        if decision.forwarded:
            result.append(TrafficDemand(src, decision.relay, decision.targets[0].volume))
            result.extend(
                TrafficDemand(decision.relay, d.destination, d.volume)
                for d in decision.forwarded
            )
            result.extend(decision.direct)
        else:
            result.extend(decision.targets)
    return result


def _selective_relay_b_decisions(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads_seed: Dict[Edge, float],
) -> tuple[List[TrafficDemand], Dict[int, RelayDecision]]:
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

    decisions: Dict[int, RelayDecision] = {}
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
            decisions[src] = RelayDecision(
                relay=None,
                targets=targets,
                forwarded=[],
                direct=list(targets),
            )
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

        decisions[src] = RelayDecision(
            relay=relay,
            targets=targets,
            forwarded=forwarded,
            direct=direct,
        )
    return passthrough, decisions


def _route_loads(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads_seed: Dict[Edge, float],
    routing_strategy: str,
) -> tuple[Dict[Edge, float], int]:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0

    if routing_strategy in {"adaptive_selective_relay_b", "async_optimized"}:
        traffic = _selective_relay_b_traffic(topology, traffic, edge_loads_seed)

    for demand in traffic:
        if routing_strategy in {
            "shortest_multipath",
            "adaptive_multipath",
            "adaptive_selective_relay_b",
            "async_optimized",
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
                "async_optimized",
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


def _compute_edge_loads(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    routing_strategy: str,
    start_times: Optional[Dict[int, int]] = None,
) -> tuple[Dict[Edge, float], int, Dict[Edge, float]]:
    edge_loads: Dict[Edge, float] = {}
    disconnected = 0
    if routing_strategy == "async_optimized":
        if start_times is None:
            rng = random.Random(ASYNC_START_SEED)
            start_times = {
                src: _poisson_sample(rng, ASYNC_START_LAMBDA)
                for src in range(A_GROUP_SIZE)
            }
        edge_loads_seed, disconnected = _compute_async_seed_loads(
            topology,
            traffic,
            routing_strategy,
            start_times,
        )
        return edge_loads_seed, disconnected, edge_loads_seed
    if routing_strategy in {
        "adaptive_multipath",
        "adaptive_selective_relay_b",
        "adaptive_bounded_multipath",
    }:
        edge_loads_seed: Dict[Edge, float] = {}
        seed_used = edge_loads_seed
        for _ in range(max(1, ROUTING_ITERATIONS)):
            seed_used = edge_loads_seed
            edge_loads, disconnected = _route_loads(
                topology,
                traffic,
                edge_loads_seed,
                routing_strategy,
            )
            edge_loads_seed = edge_loads
        return edge_loads, disconnected, seed_used
    edge_loads, disconnected = _route_loads(
        topology,
        traffic,
        edge_loads,
        routing_strategy,
    )
    return edge_loads, disconnected, {}


def _compute_async_seed_loads(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    routing_strategy: str,
    start_times: Dict[int, int],
) -> tuple[Dict[Edge, float], int]:
    edge_loads_seed: Dict[Edge, float] = {}
    disconnected = 0
    grouped: Dict[int, List[TrafficDemand]] = {}
    passthrough: List[TrafficDemand] = []
    for demand in traffic:
        if demand.source in start_times:
            grouped.setdefault(demand.source, []).append(demand)
        else:
            passthrough.append(demand)

    ordered_sources = sorted(
        grouped.keys(),
        key=lambda src: (start_times.get(src, 0), src),
    )

    def add_loads_for_demands(demands: List[TrafficDemand]) -> None:
        nonlocal disconnected
        for demand in demands:
            allocations = _path_allocations_for_demand(
                topology,
                demand,
                routing_strategy,
                edge_loads_seed,
            )
            if allocations is None:
                disconnected += 1
                continue
            for path_edges, share in allocations:
                for edge in path_edges:
                    edge_loads_seed[edge] = edge_loads_seed.get(edge, 0.0) + share

    if passthrough:
        add_loads_for_demands(passthrough)

    for src in ordered_sources:
        demands = grouped[src]
        if routing_strategy in {"adaptive_selective_relay_b", "async_optimized"}:
            source_passthrough, decisions = _selective_relay_b_decisions(
                topology,
                demands,
                edge_loads_seed,
            )
            expanded: List[TrafficDemand] = list(source_passthrough)
            decision = decisions.get(src)
            if decision is None or not decision.forwarded or decision.relay is None:
                expanded.extend(decision.targets if decision else demands)
            else:
                expanded.append(TrafficDemand(src, decision.relay, decision.targets[0].volume))
                expanded.extend(
                    TrafficDemand(decision.relay, d.destination, d.volume)
                    for d in decision.forwarded
                )
                expanded.extend(decision.direct)
            add_loads_for_demands(expanded)
        else:
            add_loads_for_demands(demands)

    return edge_loads_seed, disconnected


def _request_completion_times(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    edge_loads: Dict[Edge, float],
    routing_strategy: str,
    start_times: Dict[int, int],
) -> tuple[Dict[int, float], int]:
    grouped: Dict[int, List[TrafficDemand]] = {}
    for demand in traffic:
        if 0 <= demand.source < A_GROUP_SIZE:
            grouped.setdefault(demand.source, []).append(demand)

    decisions: Dict[int, RelayDecision] = {}
    if routing_strategy in {"adaptive_selective_relay_b", "async_optimized"}:
        _, decisions = _selective_relay_b_decisions(topology, traffic, edge_loads)

    completion_times: Dict[int, float] = {}
    disconnected_requests = 0

    for src, demands in grouped.items():
        costs: List[float] = []
        if routing_strategy == "adaptive_selective_relay_b" and src in decisions:
            decision = decisions[src]
            relay = decision.relay
            if relay is None:
                for demand in decision.targets:
                    cost = _pair_completion_cost(
                        topology,
                        demand.source,
                        demand.destination,
                        edge_loads,
                        routing_strategy,
                    )
                    if cost is None:
                        costs = []
                        break
                    costs.append(cost)
            else:
                cost_src_relay = _pair_completion_cost(
                    topology,
                    src,
                    relay,
                    edge_loads,
                    routing_strategy,
                )
                if cost_src_relay is None:
                    costs = []
                else:
                    forwarded_destinations = {
                        demand.destination for demand in decision.forwarded
                    }
                    for demand in decision.targets:
                        if demand.destination == relay:
                            costs.append(cost_src_relay)
                            continue
                        if demand.destination in forwarded_destinations:
                            cost_relay_dst = _pair_completion_cost(
                                topology,
                                relay,
                                demand.destination,
                                edge_loads,
                                routing_strategy,
                            )
                            if cost_relay_dst is None:
                                costs = []
                                break
                            costs.append(cost_src_relay + cost_relay_dst)
                        else:
                            cost_direct = _pair_completion_cost(
                                topology,
                                demand.source,
                                demand.destination,
                                edge_loads,
                                routing_strategy,
                            )
                            if cost_direct is None:
                                costs = []
                                break
                            costs.append(cost_direct)
        else:
            for demand in demands:
                cost = _pair_completion_cost(
                    topology,
                    demand.source,
                    demand.destination,
                    edge_loads,
                    routing_strategy,
                )
                if cost is None:
                    costs = []
                    break
                costs.append(cost)

        if not costs:
            disconnected_requests += 1
            continue
        completion_times[src] = start_times.get(src, 0) + max(costs)

    return completion_times, disconnected_requests


def _build_async_flow_model(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    routing_strategy: str,
    edge_loads_seed: Dict[Edge, float],
    start_times: Dict[int, int],
) -> tuple[
    List[_Flow],
    Dict[int, _DemandGroup],
    Dict[int, List[int]],
    Dict[int, List[_Flow]],
    int,
]:
    grouped: Dict[int, List[TrafficDemand]] = {}
    for demand in traffic:
        if 0 <= demand.source < A_GROUP_SIZE:
            grouped.setdefault(demand.source, []).append(demand)

    decisions: Dict[int, RelayDecision] = {}
    if routing_strategy in {"adaptive_selective_relay_b", "async_optimized"}:
        _, decisions = _selective_relay_b_decisions(topology, traffic, edge_loads_seed)

    flows: List[_Flow] = []
    demand_groups: Dict[int, _DemandGroup] = {}
    request_groups: Dict[int, List[int]] = {}
    waiting_by_group: Dict[int, List[_Flow]] = {}

    next_flow_id = 0
    next_group_id = 0
    disconnected_requests = 0

    for src, demands in grouped.items():
        start_time = float(start_times.get(src, 0))
        temp_flows: List[_Flow] = []
        temp_groups: Dict[int, _DemandGroup] = {}
        temp_request_groups: List[int] = []
        temp_waiting: Dict[int, List[_Flow]] = {}
        failed = False

        decision = decisions.get(src)
        use_relay = decision is not None and bool(decision.forwarded)
        if not use_relay:
            for demand in demands:
                allocations = _path_allocations_for_demand(
                    topology,
                    demand,
                    routing_strategy,
                    edge_loads_seed,
                )
                if allocations is None:
                    failed = True
                    break
                group_id = next_group_id
                next_group_id += 1
                temp_groups[group_id] = _DemandGroup(
                    group_id=group_id,
                    request_source=src,
                    destination=demand.destination,
                    pending_flows=len(allocations),
                )
                temp_request_groups.append(group_id)
                for path_edges, share in allocations:
                    temp_flows.append(
                        _Flow(
                            flow_id=next_flow_id,
                            group_id=group_id,
                            request_source=src,
                            path_edges=path_edges,
                            remaining=share,
                            start_time=start_time,
                            depends_on_group=None,
                        )
                    )
                    next_flow_id += 1
        else:
            relay = decision.relay
            if relay is None:
                failed = True
            else:
                relay_demand = TrafficDemand(src, relay, demands[0].volume)
                relay_allocations = _path_allocations_for_demand(
                    topology,
                    relay_demand,
                    routing_strategy,
                    edge_loads_seed,
                )
                if relay_allocations is None:
                    failed = True
                else:
                    relay_group_id = next_group_id
                    next_group_id += 1
                    temp_groups[relay_group_id] = _DemandGroup(
                        group_id=relay_group_id,
                        request_source=src,
                        destination=relay,
                        pending_flows=len(relay_allocations),
                    )
                    relay_targets = {d.destination for d in demands}
                    if relay in relay_targets:
                        temp_request_groups.append(relay_group_id)
                    for path_edges, share in relay_allocations:
                        temp_flows.append(
                            _Flow(
                                flow_id=next_flow_id,
                                group_id=relay_group_id,
                                request_source=src,
                                path_edges=path_edges,
                                remaining=share,
                                start_time=start_time,
                                depends_on_group=None,
                            )
                        )
                        next_flow_id += 1

                    forwarded_destinations = {
                        demand.destination for demand in decision.forwarded
                    }
                    for demand in demands:
                        if demand.destination == relay:
                            continue
                        if demand.destination in forwarded_destinations:
                            allocations = _path_allocations_for_demand(
                                topology,
                                TrafficDemand(relay, demand.destination, demand.volume),
                                routing_strategy,
                                edge_loads_seed,
                            )
                            if allocations is None:
                                failed = True
                                break
                            group_id = next_group_id
                            next_group_id += 1
                            temp_groups[group_id] = _DemandGroup(
                                group_id=group_id,
                                request_source=src,
                                destination=demand.destination,
                                pending_flows=len(allocations),
                            )
                            temp_request_groups.append(group_id)
                            for path_edges, share in allocations:
                                flow = _Flow(
                                    flow_id=next_flow_id,
                                    group_id=group_id,
                                    request_source=src,
                                    path_edges=path_edges,
                                    remaining=share,
                                    start_time=None,
                                    depends_on_group=relay_group_id,
                                )
                                temp_flows.append(flow)
                                temp_waiting.setdefault(relay_group_id, []).append(flow)
                                next_flow_id += 1
                        else:
                            allocations = _path_allocations_for_demand(
                                topology,
                                demand,
                                routing_strategy,
                                edge_loads_seed,
                            )
                            if allocations is None:
                                failed = True
                                break
                            group_id = next_group_id
                            next_group_id += 1
                            temp_groups[group_id] = _DemandGroup(
                                group_id=group_id,
                                request_source=src,
                                destination=demand.destination,
                                pending_flows=len(allocations),
                            )
                            temp_request_groups.append(group_id)
                            for path_edges, share in allocations:
                                temp_flows.append(
                                    _Flow(
                                        flow_id=next_flow_id,
                                        group_id=group_id,
                                        request_source=src,
                                        path_edges=path_edges,
                                        remaining=share,
                                        start_time=start_time,
                                        depends_on_group=None,
                                    )
                                )
                                next_flow_id += 1

        if failed:
            disconnected_requests += 1
            continue

        flows.extend(temp_flows)
        demand_groups.update(temp_groups)
        request_groups[src] = temp_request_groups
        for group_id, group_flows in temp_waiting.items():
            waiting_by_group.setdefault(group_id, []).extend(group_flows)

    return flows, demand_groups, request_groups, waiting_by_group, disconnected_requests


def _simulate_async_flow_dynamics(
    flows: List[_Flow],
    demand_groups: Dict[int, _DemandGroup],
    waiting_by_group: Dict[int, List[_Flow]],
) -> None:
    scheduled = [flow for flow in flows if flow.start_time is not None]
    scheduled.sort(key=lambda flow: flow.start_time or 0.0)
    active: List[_Flow] = []
    next_idx = 0
    t = 0.0
    eps = 1e-9

    while active or next_idx < len(scheduled):
        if not active:
            t = scheduled[next_idx].start_time or 0.0
            while next_idx < len(scheduled) and (scheduled[next_idx].start_time or 0.0) <= t + eps:
                active.append(scheduled[next_idx])
                next_idx += 1

        immediate = [flow for flow in active if not flow.path_edges]
        if immediate:
            active = [flow for flow in active if flow.path_edges]
            for flow in immediate:
                flow.completion_time = t
                group = demand_groups.get(flow.group_id)
                if group is None or group.completion_time is not None:
                    continue
                group.pending_flows -= 1
                if group.pending_flows <= 0:
                    group.completion_time = t
                    for pending in waiting_by_group.get(group.group_id, []):
                        pending.start_time = t
                        active.append(pending)
                    waiting_by_group.pop(group.group_id, None)
            continue

        edge_counts: Dict[Edge, int] = {}
        for flow in active:
            for edge in flow.path_edges:
                edge_counts[edge] = edge_counts.get(edge, 0) + 1

        min_finish = None
        for flow in active:
            rate = min(1.0 / edge_counts[edge] for edge in flow.path_edges)
            time_to_finish = flow.remaining / rate if rate > 0 else float("inf")
            if min_finish is None or time_to_finish < min_finish:
                min_finish = time_to_finish

        next_start = (
            scheduled[next_idx].start_time if next_idx < len(scheduled) else None
        )
        if min_finish is None:
            break
        if next_start is None:
            delta = min_finish
        else:
            delta = min(min_finish, max(0.0, (next_start or 0.0) - t))

        if delta <= 0:
            if next_start is None:
                break
            t = next_start
            while next_idx < len(scheduled) and (scheduled[next_idx].start_time or 0.0) <= t + eps:
                active.append(scheduled[next_idx])
                next_idx += 1
            continue

        for flow in active:
            rate = min(1.0 / edge_counts[edge] for edge in flow.path_edges)
            flow.remaining -= rate * delta
        t += delta

        completed: List[_Flow] = []
        still_active: List[_Flow] = []
        for flow in active:
            if flow.remaining <= eps:
                flow.completion_time = t
                completed.append(flow)
            else:
                still_active.append(flow)
        active = still_active

        for flow in completed:
            group = demand_groups.get(flow.group_id)
            if group is None or group.completion_time is not None:
                continue
            group.pending_flows -= 1
            if group.pending_flows <= 0:
                group.completion_time = t
                for pending in waiting_by_group.get(group.group_id, []):
                    pending.start_time = t
                    active.append(pending)
                waiting_by_group.pop(group.group_id, None)

        while next_idx < len(scheduled) and (scheduled[next_idx].start_time or 0.0) <= t + eps:
            active.append(scheduled[next_idx])
            next_idx += 1

def simulate(
    topology: Topology,
    traffic: Iterable[TrafficDemand],
    routing_strategy: str = ROUTING_STRATEGY,
    timing_model: str = TIMING_MODEL,
    start_times: Optional[Dict[int, int]] = None,
) -> SimulationResult:
    edge_loads, disconnected, routing_seed = _compute_edge_loads(
        topology,
        traffic,
        routing_strategy,
        start_times=start_times if timing_model == "async" else None,
    )
    max_edge_load = max(edge_loads.values(), default=0.0)
    request_time_mean = None
    request_time_variance = None
    request_completion_times = None
    communication_time = max_edge_load
    if timing_model == "async":
        if start_times is None:
            rng = random.Random(ASYNC_START_SEED)
            start_times = {
                src: _poisson_sample(rng, ASYNC_START_LAMBDA) for src in range(A_GROUP_SIZE)
            }
        (
            flows,
            demand_groups,
            request_groups,
            waiting_by_group,
            _,
        ) = _build_async_flow_model(
            topology,
            traffic,
            routing_strategy,
            routing_seed,
            start_times,
        )
        _simulate_async_flow_dynamics(flows, demand_groups, waiting_by_group)
        request_completion_times = {}
        for src, group_ids in request_groups.items():
            completion_times: List[float] = []
            for group_id in group_ids:
                group = demand_groups.get(group_id)
                if group is None or group.completion_time is None:
                    completion_times = []
                    break
                completion_times.append(group.completion_time)
            if completion_times:
                request_completion_times[src] = max(completion_times)
        times = list(request_completion_times.values())
        if times:
            request_time_mean = sum(times) / len(times)
            request_time_variance = sum(
                (t - request_time_mean) ** 2 for t in times
            ) / len(times)
            communication_time = request_time_mean
        else:
            request_time_mean = 0.0
            request_time_variance = 0.0
            communication_time = 0.0
    return SimulationResult(
        communication_time=communication_time,
        max_edge_load=max_edge_load,
        disconnected_flows=disconnected,
        edge_loads=edge_loads,
        request_time_mean=request_time_mean,
        request_time_variance=request_time_variance,
        request_completion_times=request_completion_times,
    )
