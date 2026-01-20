"""Baseline comparison utilities."""

from __future__ import annotations

import math
from typing import Iterable

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
