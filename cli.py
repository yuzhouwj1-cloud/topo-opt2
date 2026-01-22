"""Command-line interface for topology optimization."""

import argparse
import json

from baseline import (
    equivalent_switch_ports_for_traffic,
    equivalent_switch_ports_for_multicast_traffic,
    generate_async_start_times,
    switch_communication_time_for_traffic,
    switch_communication_time_for_multicast_traffic,
    switch_async_request_stats,
)
from export_drawio_svg import export_drawio_svg
from export_topology import export_topology
from optimize import optimize_topology, save_optimization
from simulate import simulate
from topo_config import (
    A_GROUP_SIZE,
    ASYNC_START_LAMBDA,
    ASYNC_START_SEED,
    DEFAULT_RANDOM_SEED,
    MOE_R,
    N,
    PORTS_PER_CHIP,
    ROUTING_STRATEGY,
    MAX_SHORTEST_PATHS,
    EXTRA_HOPS,
    ROUTING_ITERATIONS,
    TIMING_MODEL,
    TRAFFIC_MODE,
    TRAFFIC_SEED,
)
from topology import (
    build_clos_topology,
    build_dragonfly_topology,
    build_initial_topology,
)
from traffic import generate_traffic, serialize_traffic, traffic_matrix
from traffic_heatmap import plot_traffic_heatmap
from visualize_history import plot_history
from visualize_topology import visualize_topology


def compute_port_utilization(
    edge_loads: dict[tuple[int, int], float],
    communication_time: float,
    node_count: int,
    ports_per_chip: int,
) -> list[float]:
    totals = [0.0 for _ in range(node_count)]
    for (node_a, node_b), load in edge_loads.items():
        totals[node_a] += load
        totals[node_b] += load
    capacity = ports_per_chip * communication_time
    if capacity <= 0:
        return [0.0 for _ in range(node_count)]
    return [total / capacity for total in totals]


def compute_degrees(edges: list[tuple[int, int]], node_count: int) -> list[int]:
    degrees = [0 for _ in range(node_count)]
    for node_a, node_b in edges:
        degrees[node_a] += 1
        degrees[node_b] += 1
    return degrees


def compute_effective_bandwidth(
    edge_loads: dict[tuple[int, int], float],
    communication_time: float,
    node_count: int,
) -> list[float]:
    totals = [0.0 for _ in range(node_count)]
    for (node_a, node_b), load in edge_loads.items():
        totals[node_a] += load
        totals[node_b] += load
    if communication_time <= 0:
        return [0.0 for _ in range(node_count)]
    return [total / communication_time for total in totals]


def handle_generate_traffic(args: argparse.Namespace) -> None:
    traffic = generate_traffic(
        mode=args.traffic_mode,
        moe_r=args.moe_r,
        seed=args.traffic_seed,
    )
    payload = serialize_traffic(traffic)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    if args.heatmap_output:
        plot_traffic_heatmap(traffic, args.heatmap_output)


def handle_simulate(args: argparse.Namespace) -> None:
    traffic = generate_traffic(
        mode=args.traffic_mode,
        moe_r=args.moe_r,
        seed=args.traffic_seed,
    )
    topology = build_initial_topology(seed=args.seed)
    result = simulate(
        topology,
        traffic,
        routing_strategy=args.routing_strategy,
        timing_model=args.timing_model,
    )
    print(result)


def handle_optimize(args: argparse.Namespace) -> None:
    start_times = None
    if args.timing_model == "async":
        start_times = generate_async_start_times(
            A_GROUP_SIZE,
            ASYNC_START_LAMBDA,
            ASYNC_START_SEED,
        )
    result = optimize_topology(
        iterations=args.iterations,
        seed=args.seed,
        resume_path=args.resume_path,
        traffic_mode=args.traffic_mode,
        moe_r=args.moe_r,
        traffic_seed=args.traffic_seed,
        routing_strategy=args.routing_strategy,
        timing_model=args.timing_model,
        start_times=start_times,
    )
    save_optimization(result, args.output)
    drawio_path, svg_path = export_drawio_svg(
        result.best_topology,
        args.drawio_output,
        args.svg_output,
    )
    best_time = result.best_result.communication_time
    history_plot = plot_history(result.history, args.history_plot)
    topology_plot = visualize_topology(result.best_topology, path=args.topology_plot)
    history_times = [item.communication_time for item in result.history]
    utilization = compute_port_utilization(
        result.best_result.edge_loads,
        best_time,
        N,
        PORTS_PER_CHIP,
    )
    degrees = compute_degrees(result.best_topology.edges(), N)
    avg_degree = sum(degrees) / N if N else 0.0
    effective_bandwidth = compute_effective_bandwidth(
        result.best_result.edge_loads,
        best_time,
        N,
    )
    avg_effective_bandwidth = sum(effective_bandwidth) / N if N else 0.0
    routing_config = {
        "strategy": args.routing_strategy,
        "max_shortest_paths": MAX_SHORTEST_PATHS,
        "extra_hops": EXTRA_HOPS,
        "routing_iterations": ROUTING_ITERATIONS,
        "timing_model": args.timing_model,
    }
    traffic = generate_traffic(
        mode=args.traffic_mode,
        moe_r=args.moe_r,
        seed=args.traffic_seed,
    )
    use_multicast = args.traffic_mode == "moe"
    if use_multicast:
        ports_needed = equivalent_switch_ports_for_multicast_traffic(best_time, traffic)
    else:
        ports_needed = equivalent_switch_ports_for_traffic(best_time, traffic)

    switch_time_variance = None
    switch_time_4_variance = None
    if args.timing_model == "async" and start_times is not None:
        _, switch_time, switch_time_variance = switch_async_request_stats(
            traffic,
            ports_needed,
            start_times,
        )
        _, switch_time_4, switch_time_4_variance = switch_async_request_stats(
            traffic,
            4,
            start_times,
        )
    else:
        if use_multicast:
            switch_time = switch_communication_time_for_multicast_traffic(traffic, ports_needed)
            switch_time_4 = switch_communication_time_for_multicast_traffic(traffic, 4)
        else:
            switch_time = switch_communication_time_for_traffic(traffic, ports_needed)
            switch_time_4 = switch_communication_time_for_traffic(traffic, 4)
    payload = {
        "best_result": {
            "communication_time": result.best_result.communication_time,
            "max_edge_load": result.best_result.max_edge_load,
            "disconnected_flows": result.best_result.disconnected_flows,
            "request_time_mean": result.best_result.request_time_mean,
            "request_time_variance": result.best_result.request_time_variance,
        },
        "switch_baseline": {
            "ports_per_chip": ports_needed,
            "communication_time": switch_time,
            "variance": switch_time_variance,
        },
        "switch_4_port_time": switch_time_4,
        "switch_4_port_variance": switch_time_4_variance,
        "traffic_matrix": traffic_matrix(traffic=traffic),
        "port_utilization": utilization,
        "history_plot": history_plot,
        "history_times": history_times,
        "topology_plot": topology_plot,
        "drawio_path": drawio_path,
        "svg_path": svg_path,
        "routing_config": routing_config,
        "traffic_config": {
            "mode": args.traffic_mode,
            "moe_r": args.moe_r,
            "seed": args.traffic_seed,
        },
        "degrees": degrees,
        "avg_degree": avg_degree,
        "effective_bandwidth": effective_bandwidth,
        "avg_effective_bandwidth": avg_effective_bandwidth,
    }
    with open(args.summary_output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps(payload, indent=2))
    print("[optimize] routing_strategy=%s" % args.routing_strategy)
    print("[optimize] communication_time=%.6f" % best_time)
    print("[optimize] switch_4_port_time=%.6f" % switch_time_4)
    if switch_time_4_variance is not None:
        print("[optimize] switch_4_port_variance=%.6f" % switch_time_4_variance)
    print("[optimize] topology_edges=%s" % result.best_topology.edges())
    print("[optimize] degrees=%s avg_degree=%.3f" % (degrees, avg_degree))
    print(
        "[optimize] effective_bandwidth=%s avg_effective_bandwidth=%.6f"
        % (effective_bandwidth, avg_effective_bandwidth)
    )


def handle_export(args: argparse.Namespace) -> None:
    topology = build_initial_topology(seed=args.seed)
    export_topology(topology, args.output)


def handle_visualize(args: argparse.Namespace) -> None:
    from visualize_topology import visualize_topology

    topology = build_initial_topology(seed=args.seed)
    visualize_topology(topology, path=args.output)


def handle_compare_switch(args: argparse.Namespace) -> None:
    start_times = None
    if args.timing_model == "async":
        start_times = generate_async_start_times(
            A_GROUP_SIZE,
            ASYNC_START_LAMBDA,
            ASYNC_START_SEED,
        )
    result = optimize_topology(
        iterations=args.iterations,
        seed=args.seed,
        traffic_mode=args.traffic_mode,
        moe_r=args.moe_r,
        traffic_seed=args.traffic_seed,
        routing_strategy=args.routing_strategy,
        timing_model=args.timing_model,
        start_times=start_times,
    )
    traffic = generate_traffic(
        mode=args.traffic_mode,
        moe_r=args.moe_r,
        seed=args.traffic_seed,
    )
    best_time = result.best_result.communication_time
    use_multicast = args.traffic_mode == "moe"
    if use_multicast:
        ports_needed = equivalent_switch_ports_for_multicast_traffic(best_time, traffic)
    else:
        ports_needed = equivalent_switch_ports_for_traffic(best_time, traffic)
    switch_time_variance = None
    switch_time_4_variance = None
    if args.timing_model == "async" and start_times is not None:
        _, switch_time, switch_time_variance = switch_async_request_stats(
            traffic,
            ports_needed,
            start_times,
        )
        _, switch_time_4, switch_time_4_variance = switch_async_request_stats(
            traffic,
            4,
            start_times,
        )
    else:
        if use_multicast:
            switch_time = switch_communication_time_for_multicast_traffic(traffic, ports_needed)
            switch_time_4 = switch_communication_time_for_multicast_traffic(traffic, 4)
        else:
            switch_time = switch_communication_time_for_traffic(traffic, ports_needed)
            switch_time_4 = switch_communication_time_for_traffic(traffic, 4)
    payload = {
        "best_time": best_time,
        "ports_needed": ports_needed,
        "switch_time": switch_time,
        "switch_4_port_time": switch_time_4,
        "switch_time_variance": switch_time_variance,
        "switch_4_port_variance": switch_time_4_variance,
    }
    print(json.dumps(payload, indent=2))


def handle_generate_topology(args: argparse.Namespace) -> None:
    dragonfly = build_dragonfly_topology(
        groups=args.dragonfly_groups,
        routers_per_group=args.dragonfly_routers_per_group,
        global_links_per_router=args.dragonfly_global_links,
    )
    clos = build_clos_topology(
        pods=args.clos_pods,
        edge_per_pod=args.clos_edge_per_pod,
        agg_per_pod=args.clos_agg_per_pod,
        core_switches=args.clos_core_switches,
        ports_per_switch=args.ports_per_switch,
    )

    dragonfly_nodes = len(dragonfly.nodes())
    clos_nodes = len(clos.nodes())
    if dragonfly_nodes != clos_nodes:
        raise ValueError(
            "dragonfly nodes (%d) != clos nodes (%d)" % (dragonfly_nodes, clos_nodes)
        )

    max_df_degree = max((dragonfly.degree(n) for n in dragonfly.nodes()), default=0)
    max_clos_degree = max((clos.degree(n) for n in clos.nodes()), default=0)
    if max_df_degree > args.ports_per_switch:
        raise ValueError("dragonfly degree exceeds ports_per_switch")
    if max_clos_degree > args.ports_per_switch:
        raise ValueError("clos degree exceeds ports_per_switch")

    export_topology(dragonfly, args.dragonfly_output)
    export_topology(clos, args.clos_output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Topology optimization toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    traffic_parser = subparsers.add_parser("generate-traffic", help="Generate traffic file")
    traffic_parser.add_argument("--output", default="traffic.json")
    traffic_parser.add_argument(
        "--traffic-mode",
        choices=["full_mesh", "moe", "moe_two_stage_b"],
        default=TRAFFIC_MODE,
    )
    traffic_parser.add_argument("--moe-r", type=int, default=MOE_R)
    traffic_parser.add_argument("--traffic-seed", type=int, default=TRAFFIC_SEED)
    traffic_parser.add_argument(
        "--heatmap-output",
        default="artifacts/traffic_heatmap.png",
        help="Path to save traffic heatmap image.",
    )
    traffic_parser.set_defaults(func=handle_generate_traffic)

    simulate_parser = subparsers.add_parser("simulate", help="Simulate initial topology")
    simulate_parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    simulate_parser.add_argument(
        "--traffic-mode",
        choices=["full_mesh", "moe", "moe_two_stage_b"],
        default=TRAFFIC_MODE,
    )
    simulate_parser.add_argument("--moe-r", type=int, default=MOE_R)
    simulate_parser.add_argument("--traffic-seed", type=int, default=TRAFFIC_SEED)
    simulate_parser.add_argument(
        "--routing-strategy",
        choices=[
            "shortest_multipath",
            "adaptive_multipath",
            "bounded_multipath",
            "adaptive_bounded_multipath",
            "adaptive_selective_relay_b",
            "async_optimized",
        ],
        default=ROUTING_STRATEGY,
    )
    simulate_parser.add_argument(
        "--timing-model",
        choices=["sync", "async"],
        default=TIMING_MODEL,
    )
    simulate_parser.set_defaults(func=handle_simulate)

    optimize_parser = subparsers.add_parser("optimize", help="Run optimization")
    optimize_parser.add_argument("--iterations", type=int, default=200)
    optimize_parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    optimize_parser.add_argument("--output", default="optimization_result.json")
    optimize_parser.add_argument(
        "--traffic-mode",
        choices=["full_mesh", "moe", "moe_two_stage_b"],
        default=TRAFFIC_MODE,
    )
    optimize_parser.add_argument("--moe-r", type=int, default=MOE_R)
    optimize_parser.add_argument("--traffic-seed", type=int, default=TRAFFIC_SEED)
    optimize_parser.add_argument(
        "--routing-strategy",
        choices=[
            "shortest_multipath",
            "adaptive_multipath",
            "bounded_multipath",
            "adaptive_bounded_multipath",
            "adaptive_selective_relay_b",
            "async_optimized",
        ],
        default=ROUTING_STRATEGY,
    )
    optimize_parser.add_argument(
        "--timing-model",
        choices=["sync", "async"],
        default=TIMING_MODEL,
    )
    optimize_parser.add_argument(
        "--resume-path",
        default=None,
        help="Path to a JSON file containing a saved topology edges list.",
    )
    optimize_parser.add_argument(
        "--topology-plot",
        default="artifacts/topology.png",
        help="Path to save a topology visualization (requires matplotlib/networkx).",
    )
    optimize_parser.add_argument(
        "--history-plot",
        default="artifacts/optimization_history.png",
        help="Path to save iteration vs communication time plot.",
    )
    optimize_parser.add_argument(
        "--drawio-output",
        default="artifacts/topology.drawio",
        help="Path to save draw.io diagram output.",
    )
    optimize_parser.add_argument(
        "--svg-output",
        default="artifacts/topology.svg",
        help="Path to save SVG diagram output.",
    )
    optimize_parser.add_argument(
        "--summary-output",
        default="optimization_summary.json",
        help="Path to save the optimization summary JSON.",
    )
    optimize_parser.set_defaults(func=handle_optimize)

    export_parser = subparsers.add_parser("export", help="Export initial topology")
    export_parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    export_parser.add_argument("--output", default="topology.json")
    export_parser.set_defaults(func=handle_export)

    visualize_parser = subparsers.add_parser("visualize", help="Visualize topology")
    visualize_parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    visualize_parser.add_argument("--output", default=None)
    visualize_parser.set_defaults(func=handle_visualize)

    compare_parser = subparsers.add_parser(
        "compare-switch",
        help="Compare optimized topology with switch baseline",
    )
    compare_parser.add_argument("--iterations", type=int, default=200)
    compare_parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED)
    compare_parser.add_argument(
        "--traffic-mode",
        choices=["full_mesh", "moe", "moe_two_stage_b"],
        default=TRAFFIC_MODE,
    )
    compare_parser.add_argument("--moe-r", type=int, default=MOE_R)
    compare_parser.add_argument("--traffic-seed", type=int, default=TRAFFIC_SEED)
    compare_parser.add_argument(
        "--routing-strategy",
        choices=[
            "shortest_multipath",
            "adaptive_multipath",
            "bounded_multipath",
            "adaptive_bounded_multipath",
            "adaptive_selective_relay_b",
            "async_optimized",
        ],
        default=ROUTING_STRATEGY,
    )
    compare_parser.add_argument(
        "--timing-model",
        choices=["sync", "async"],
        default=TIMING_MODEL,
    )
    compare_parser.set_defaults(func=handle_compare_switch)

    topology_parser = subparsers.add_parser(
        "generate-topology",
        help="Generate dragonfly and Clos topologies with matching node counts.",
    )
    topology_parser.add_argument("--dragonfly-output", required=True)
    topology_parser.add_argument("--clos-output", required=True)
    topology_parser.add_argument("--ports-per-switch", type=int, default=PORTS_PER_CHIP)
    topology_parser.add_argument("--dragonfly-groups", type=int, required=True)
    topology_parser.add_argument("--dragonfly-routers-per-group", type=int, required=True)
    topology_parser.add_argument("--dragonfly-global-links", type=int, required=True)
    topology_parser.add_argument("--clos-pods", type=int, required=True)
    topology_parser.add_argument("--clos-edge-per-pod", type=int, required=True)
    topology_parser.add_argument("--clos-agg-per-pod", type=int, required=True)
    topology_parser.add_argument("--clos-core-switches", type=int, required=True)
    topology_parser.set_defaults(func=handle_generate_topology)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
