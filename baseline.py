"""Baseline comparison utilities."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from topo_config import A_GROUP_SIZE, B_GROUP_SIZE, TRAFFIC_VOLUME
from traffic import TrafficDemand


def switch_communication_time(
    ports_per_chip: int,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
) -> float:
    """Compute communication time for a non-blocking switch.

    Assumes each chip has `ports_per_chip` identical ports connected to a shared switch.
    Each chip can inject/receive `ports_per_chip` units of bandwidth concurrently.
    """
    if ports_per_chip <= 0:
        raise ValueError("ports_per_chip must be positive")
    per_source = b_size * volume / ports_per_chip
    per_sink = a_size * volume / ports_per_chip
    return max(per_source, per_sink)


def equivalent_switch_ports(
    target_time: float,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
) -> int:
    """Compute the minimum switch ports per chip to match a target time."""
    if target_time <= 0:
        raise ValueError("target_time must be positive")
    demand = max(a_size, b_size) * volume
    return math.ceil(demand / target_time)


def switch_communication_time_for_traffic(
    traffic: Iterable[TrafficDemand],
    ports_per_chip: int,
) -> float:
    """Compute switch time based on actual traffic demand volumes."""
    if ports_per_chip <= 0:
        raise ValueError("ports_per_chip must be positive")
    source_totals = {}
    dest_totals = {}
    for demand in traffic:
        source_totals[demand.source] = source_totals.get(demand.source, 0.0) + demand.volume
        dest_totals[demand.destination] = dest_totals.get(demand.destination, 0.0) + demand.volume
    max_source = max(source_totals.values(), default=0.0)
    max_dest = max(dest_totals.values(), default=0.0)
    return max(max_source / ports_per_chip, max_dest / ports_per_chip)


def generate_async_start_times(
    node_count: int,
    lam: float,
    seed: int,
) -> Dict[int, int]:
    rng = random.Random(seed)
    return {node: _poisson_sample(rng, lam) for node in range(node_count)}


@dataclass
class _AsyncFlow:
    source: int
    destination: int
    remaining: float
    start_time: float
    rate: float = 0.0
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


def switch_async_request_stats(
    traffic: Iterable[TrafficDemand],
    ports_per_chip: int,
    start_times: Dict[int, int],
) -> Tuple[Dict[int, float], float, float]:
    if ports_per_chip <= 0:
        raise ValueError("ports_per_chip must be positive")

    flows = [
        _AsyncFlow(
            source=demand.source,
            destination=demand.destination,
            remaining=demand.volume,
            start_time=float(start_times.get(demand.source, 0)),
        )
        for demand in traffic
    ]
    flows.sort(key=lambda flow: flow.start_time)

    active: list[_AsyncFlow] = []
    next_idx = 0
    t = 0.0
    eps = 1e-9

    while active or next_idx < len(flows):
        if not active:
            t = flows[next_idx].start_time
            while next_idx < len(flows) and flows[next_idx].start_time <= t + eps:
                active.append(flows[next_idx])
                next_idx += 1

        outgoing: Dict[int, int] = {}
        incoming: Dict[int, int] = {}
        for flow in active:
            outgoing[flow.source] = outgoing.get(flow.source, 0) + 1
            incoming[flow.destination] = incoming.get(flow.destination, 0) + 1

        min_finish = None
        for flow in active:
            src_rate = ports_per_chip / outgoing[flow.source]
            dst_rate = ports_per_chip / incoming[flow.destination]
            flow.rate = src_rate if src_rate < dst_rate else dst_rate
            time_to_finish = flow.remaining / flow.rate
            if min_finish is None or time_to_finish < min_finish:
                min_finish = time_to_finish

        next_start = flows[next_idx].start_time if next_idx < len(flows) else None
        if next_start is None:
            delta = min_finish
        else:
            delta = min(min_finish, max(0.0, next_start - t))

        for flow in active:
            flow.remaining -= flow.rate * delta
        t += delta

        if delta > 0:
            still_active = []
            for flow in active:
                if flow.remaining <= eps:
                    flow.completion_time = t
                else:
                    still_active.append(flow)
            active = still_active

        while next_idx < len(flows) and flows[next_idx].start_time <= t + eps:
            active.append(flows[next_idx])
            next_idx += 1

    request_completion_times: Dict[int, float] = {}
    for flow in flows:
        if flow.completion_time is None:
            continue
        current = request_completion_times.get(flow.source)
        if current is None or flow.completion_time > current:
            request_completion_times[flow.source] = flow.completion_time

    times = list(request_completion_times.values())
    if not times:
        return request_completion_times, 0.0, 0.0
    mean = sum(times) / len(times)
    variance = sum((t - mean) ** 2 for t in times) / len(times)
    return request_completion_times, mean, variance


def switch_communication_time_for_multicast_traffic(
    traffic: Iterable[TrafficDemand],
    ports_per_chip: int,
) -> float:
    """Compute switch time assuming each source sends one shared payload to all targets."""
    if ports_per_chip <= 0:
        raise ValueError("ports_per_chip must be positive")
    source_totals = {}
    dest_totals = {}
    for demand in traffic:
        source_totals[demand.source] = max(
            source_totals.get(demand.source, 0.0),
            demand.volume,
        )
        dest_totals[demand.destination] = dest_totals.get(demand.destination, 0.0) + demand.volume
    max_source = max(source_totals.values(), default=0.0)
    max_dest = max(dest_totals.values(), default=0.0)
    return max(max_source / ports_per_chip, max_dest / ports_per_chip)


def equivalent_switch_ports_for_traffic(
    target_time: float,
    traffic: Iterable[TrafficDemand],
) -> int:
    """Compute switch ports needed to match target time for given traffic."""
    if target_time <= 0:
        raise ValueError("target_time must be positive")
    source_totals = {}
    dest_totals = {}
    for demand in traffic:
        source_totals[demand.source] = source_totals.get(demand.source, 0.0) + demand.volume
        dest_totals[demand.destination] = dest_totals.get(demand.destination, 0.0) + demand.volume
    max_source = max(source_totals.values(), default=0.0)
    max_dest = max(dest_totals.values(), default=0.0)
    demand = max(max_source, max_dest)
    return max(1, math.ceil(demand / target_time))


def equivalent_switch_ports_for_multicast_traffic(
    target_time: float,
    traffic: Iterable[TrafficDemand],
) -> int:
    """Compute switch ports needed assuming each source sends one shared payload."""
    if target_time <= 0:
        raise ValueError("target_time must be positive")
    source_totals = {}
    dest_totals = {}
    for demand in traffic:
        source_totals[demand.source] = max(
            source_totals.get(demand.source, 0.0),
            demand.volume,
        )
        dest_totals[demand.destination] = dest_totals.get(demand.destination, 0.0) + demand.volume
    max_source = max(source_totals.values(), default=0.0)
    max_dest = max(dest_totals.values(), default=0.0)
    demand = max(max_source, max_dest)
    return max(1, math.ceil(demand / target_time))
