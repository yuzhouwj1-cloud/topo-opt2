"""Optimization loop for topology search."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import random
from typing import List

from simulate import SimulationResult, simulate
from topo_config import (
    COOLING_RATE,
    DEFAULT_RANDOM_SEED,
    DISCONNECTED_PENALTY,
    EARLY_STOP_PATIENCE,
    INITIAL_TEMPERATURE,
    MIN_ITERATIONS,
    N,
    REWIRE_EDGES,
    RESUME_STATE_PATH,
    SEARCH_STRATEGY,
    STAGNATION_LIMIT,
    SWAP_EDGES,
    CANDIDATE_POOL,
)
from topology import (
    Topology,
    build_initial_topology,
    random_rewire,
    random_swap_edges,
    topology_from_edges,
)
from traffic import TrafficDemand, generate_full_mesh_traffic


@dataclass
class OptimizationResult:
    best_topology: Topology
    best_result: SimulationResult
    history: List[SimulationResult]


def optimize_topology(
    iterations: int = 200,
    seed: int = DEFAULT_RANDOM_SEED,
    resume_path: str | None = RESUME_STATE_PATH,
) -> OptimizationResult:
    rng = random.Random(seed)
    traffic = generate_full_mesh_traffic()
    current_topology = build_initial_topology(seed=seed)
    current_result = simulate(current_topology, traffic)

    if resume_path and os.path.exists(resume_path):
        with open(resume_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        edges = payload.get("edges", [])
        if edges:
            current_topology = topology_from_edges(edges, N)
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
    no_improve = 0

    min_iterations = max(MIN_ITERATIONS, 1)

    for step in range(iterations):
        candidate_topology = None
        candidate_result = None
        candidate_score = None
        for _ in range(max(1, CANDIDATE_POOL)):
            proposal = Topology(
                adjacency={k: set(v) for k, v in current_topology.adjacency.items()}
            )
            for _ in range(max(1, REWIRE_EDGES)):
                proposal = random_rewire(
                    proposal,
                    seed=rng.randint(0, 10**9),
                )
            for _ in range(max(0, SWAP_EDGES)):
                proposal = random_swap_edges(
                    proposal,
                    seed=rng.randint(0, 10**9),
                )
            proposal_result = simulate(proposal, traffic)
            history.append(proposal_result)
            proposal_score = score(proposal_result)
            if candidate_score is None or proposal_score < candidate_score:
                candidate_topology = proposal
                candidate_result = proposal_result
                candidate_score = proposal_score
        if candidate_topology is None or candidate_result is None or candidate_score is None:
            continue

        if candidate_score < best_score:
            best_topology = candidate_topology
            best_result = candidate_result
            best_score = candidate_score
            stagnation = 0
            no_improve = 0
        else:
            stagnation += 1
            no_improve += 1

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
            no_improve = 0

        if step + 1 >= min_iterations and no_improve >= EARLY_STOP_PATIENCE:
            break

        if (step + 1) % 50 == 0:
            print(
                "[optimize] step=%d best_time=%.6f current_time=%.6f temp=%.4f"
                % (
                    step + 1,
                    best_result.communication_time,
                    current_result.communication_time,
                    temperature,
                )
            )

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
