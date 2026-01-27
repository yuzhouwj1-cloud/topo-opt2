"""Traffic generation utilities."""

from dataclasses import dataclass
import random
from typing import Iterable, List, Optional

from topo_config import (
    A_GROUP_SIZE,
    B_GROUP_SIZE,
    DEFAULT_RANDOM_SEED,
    MOE_R,
    N,
    TRAFFIC_MODE,
    TRAFFIC_VOLUME,
)


@dataclass(frozen=True)
class TrafficDemand:
    source: int
    destination: int
    volume: float


def generate_full_mesh_traffic(
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
) -> List[TrafficDemand]:
    """Generate full a->b traffic demands."""
    traffic = []
    for src in range(a_size):
        for dst in range(a_size, a_size + b_size):
            traffic.append(TrafficDemand(src, dst, volume))
    return traffic


def generate_moe_traffic(
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
    r: int = MOE_R,
    seed: int = DEFAULT_RANDOM_SEED,
) -> List[TrafficDemand]:
    """Generate MoE-style traffic: each a node sends to r random b nodes."""
    rng = random.Random(seed)
    traffic = []
    pool = list(range(a_size, a_size + b_size))
    count = min(max(r, 0), b_size)
    for src in range(a_size):
        targets = rng.sample(pool, count) if count > 0 else []
        for dst in targets:
            traffic.append(TrafficDemand(src, dst, volume))
    return traffic


def generate_moe_two_stage_b_traffic(
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
    r: int = MOE_R,
    seed: int = DEFAULT_RANDOM_SEED,
) -> List[TrafficDemand]:
    """Generate MoE two-stage traffic with relays inside group B."""
    rng = random.Random(seed)
    traffic = []
    pool = list(range(a_size, a_size + b_size))
    count = min(max(r, 0), b_size)
    for src in range(a_size):
        targets = rng.sample(pool, count) if count > 0 else []
        if not targets:
            continue
        relay = rng.choice(targets)
        traffic.append(TrafficDemand(src, relay, volume))
        for dst in targets:
            if dst == relay:
                continue
            traffic.append(TrafficDemand(relay, dst, volume))
    return traffic


def generate_traffic(
    mode: str = TRAFFIC_MODE,
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    volume: float = TRAFFIC_VOLUME,
    moe_r: int = MOE_R,
    seed: int = DEFAULT_RANDOM_SEED,
) -> List[TrafficDemand]:
    """Generate traffic demands based on the selected mode."""
    if mode == "full_mesh":
        return generate_full_mesh_traffic(a_size=a_size, b_size=b_size, volume=volume)
    if mode == "moe":
        return generate_moe_traffic(
            a_size=a_size,
            b_size=b_size,
            volume=volume,
            r=moe_r,
            seed=seed,
        )
    if mode == "moe_two_stage_b":
        return generate_moe_two_stage_b_traffic(
            a_size=a_size,
            b_size=b_size,
            volume=volume,
            r=moe_r,
            seed=seed,
        )
    raise ValueError(f"Unsupported traffic mode: {mode}")


def serialize_traffic(traffic: Iterable[TrafficDemand]) -> List[dict]:
    return [
        {"source": t.source, "destination": t.destination, "volume": t.volume}
        for t in traffic
    ]


def traffic_matrix(
    a_size: int = A_GROUP_SIZE,
    b_size: int = B_GROUP_SIZE,
    node_count: int = N,
    traffic: Optional[Iterable[TrafficDemand]] = None,
) -> List[List[int]]:
    matrix = [[0 for _ in range(node_count)] for _ in range(node_count)]
    if traffic is None:
        traffic = generate_full_mesh_traffic(a_size=a_size, b_size=b_size)
    for demand in traffic:
        matrix[demand.source][demand.destination] = 1
    return matrix
