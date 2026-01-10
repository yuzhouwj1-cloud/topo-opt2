"""Baseline comparison utilities."""

from __future__ import annotations

import math

from topo_config import A_GROUP_SIZE, B_GROUP_SIZE, TRAFFIC_VOLUME


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
