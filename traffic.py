"""Traffic generation utilities."""

from dataclasses import dataclass
from typing import Iterable, List

from topo_config import A_GROUP_SIZE, B_GROUP_SIZE, TRAFFIC_VOLUME


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


def serialize_traffic(traffic: Iterable[TrafficDemand]) -> List[dict]:
    return [
        {"source": t.source, "destination": t.destination, "volume": t.volume}
        for t in traffic
    ]
