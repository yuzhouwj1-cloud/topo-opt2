"""Optimization loop for topology search."""

from __future__ import annotations

from dataclasses import dataclass
import json
import random
from typing import List

from simulate import SimulationResult, simulate
from topo_config import (
    COOLING_RATE,
    DEFAULT_RANDOM_SEED,
    DISCONNECTED_PENALTY,
    INITIAL_TEMPERATURE,
    REWIRE_EDGES,
    SEARCH_STRATEGY,
    STAGNATION_LIMIT,
    SWAP_EDGES,
)
from topology import Topology, build_initial_topology, random_rewire, random_swap_edges
from traffic import TrafficDemand, generate_full_mesh_traffic


@dataclass
class OptimizationResult:
    best_topology: Topology
    best_result: SimulationResult
    history: List[SimulationResult]


def optimize_topology(
    iterations: int = 200,
    seed: int = DEFAULT_RANDOM_SEED,
) -> OptimizationResult:
    rng = random.Random(seed)
    traffic = generate_full_mesh_traffic()
    current_topology = build_initial_topology(seed=seed)
    current_result = simulate(current_topology, traffic)

    best_topology = current_topology
    best_result = current_result
    history = [current_result]

    temperature = INITIAL_TEMPERATURE

    def score(result: SimulationResult) -> float:
        return result.communication_time + result.disconnected_flows * DISCONNECTED_PENALTY

    current_score = score(current_result)
    best_score = current_score
    stagnation = 0

    for _ in range(iterations):
        candidate_topology = Topology(
            adjacency={k: set(v) for k, v in current_topology.adjacency.items()}
        )
        for _ in range(max(1, REWIRE_EDGES)):
            candidate_topology = random_rewire(
                candidate_topology,
                seed=rng.randint(0, 10**9),
            )
        for _ in range(max(0, SWAP_EDGES)):
            candidate_topology = random_swap_edges(
                candidate_topology,
                seed=rng.randint(0, 10**9),
            )
        candidate_result = simulate(candidate_topology, traffic)
        history.append(candidate_result)
        candidate_score = score(candidate_result)

        if candidate_score < best_score:
            best_topology = candidate_topology
            best_result = candidate_result
            best_score = candidate_score
            stagnation = 0
        else:
            stagnation += 1

        if SEARCH_STRATEGY == "simulated_annealing":
            delta = candidate_score - current_score
            accept = delta <= 0 or rng.random() < pow(2.718281828, -delta / max(temperature, 1e-6))
            if accept:
                current_topology = candidate_topology
                current_result = candidate_result
                current_score = candidate_score
            temperature *= COOLING_RATE
        else:
            if candidate_score <= current_score:
                current_topology = candidate_topology
                current_result = candidate_result
                current_score = candidate_score

        if stagnation >= STAGNATION_LIMIT:
            current_topology = build_initial_topology(seed=rng.randint(0, 10**9))
            current_result = simulate(current_topology, traffic)
            current_score = score(current_result)
            temperature = INITIAL_TEMPERATURE
            stagnation = 0

    return OptimizationResult(best_topology, best_result, history)


def save_optimization(result: OptimizationResult, path: str) -> None:
    payload = {
        "best_result": {
            "communication_time": result.best_result.communication_time,
            "max_edge_load": result.best_result.max_edge_load,
            "disconnected_flows": result.best_result.disconnected_flows,
        },
        "history": [
            {
                "communication_time": item.communication_time,
                "max_edge_load": item.max_edge_load,
                "disconnected_flows": item.disconnected_flows,
            }
            for item in result.history
        ],
        "edges": result.best_topology.edges(),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


if __name__ == "__main__":
    result = optimize_topology()
    save_optimization(result, "optimization_result.json")
