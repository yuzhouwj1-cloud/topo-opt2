# Work Log - Topology Optimization Experiments

This log summarizes the experiments run in this session for N=128 chips (A=64, B=64),
the routing strategy used, and the outputs needed to reproduce results.

## Environment
- Commands executed with `python3` in `/Users/yuzhou/Documents/topo-opt2`
- Random seed: 42 (unless noted)

## Current config snapshot
- `N=128`, `A_GROUP_SIZE=64`, `B_GROUP_SIZE=64`
- `PORTS_PER_CHIP=12` (latest state)
- `ALLOW_INTRA_GROUP=True` (latest state)
- Routing:
  - `ROUTING_STRATEGY=adaptive_multipath`
  - `MAX_SHORTEST_PATHS=16`
  - `EXTRA_HOPS=1`
  - `ROUTING_ITERATIONS=4`

## Routing strategy summary
- `adaptive_multipath`: enumerate shortest paths (up to `MAX_SHORTEST_PATHS`), then
  split flow inversely proportional to current edge load (iterated for
  `ROUTING_ITERATIONS`).
- `adaptive_bounded_multipath`: bounded shortest paths (allows `EXTRA_HOPS`)
  with the same adaptive load-aware splitting.

## Code changes (compatibility)
- Replaced `|` union types with `Optional`/`Union` for older Python compatibility:
  - `export_drawio_svg.py`, `topology.py`, `simulate.py`, `optimize.py`,
    `visualize_topology.py`.

## Experiment matrix

### d=16 (PORTS_PER_CHIP=16)
- Command:
  - `python3 cli.py optimize --iterations 10 --seed 42 --output optimization_result.json`
- Result:
  - `communication_time=13.203559676020733`
  - 4-port switch baseline time: `16.0` (better than switch)
- Outputs:
  - Topology: `optimization_result.json` (key: `edges`)
  - Summary: `optimization_summary.json`
  - Draw.io/SVG: `artifacts/topology.drawio`, `artifacts/topology.svg`

### d=15
- Command:
  - `python3 cli.py optimize --iterations 10 --seed 42 --output optimization_result_d15.json --summary-output artifacts/summary_d15.json`
- Result:
  - `communication_time=13.719435172734041` (better than 4-port switch)
- Outputs:
  - Topology: `optimization_result_d15.json`
  - Summary: `artifacts/summary_d15.json`

### d=14
- Command:
  - `python3 cli.py optimize --iterations 10 --seed 42 --output optimization_result_d14.json --summary-output artifacts/summary_d14.json`
- Result:
  - `communication_time=14.366417501073185` (better than 4-port switch)
- Outputs:
  - Topology: `optimization_result_d14.json`
  - Summary: `artifacts/summary_d14.json`

### d=13
- Command:
  - `python3 cli.py optimize --iterations 10 --seed 42 --output optimization_result_d13.json --summary-output artifacts/summary_d13.json`
- Result:
  - `communication_time=15.469623028715334` (better than 4-port switch)
- Outputs:
  - Topology: `optimization_result_d13.json`
  - Summary: `artifacts/summary_d13.json`

### d=12 (ALLOW_INTRA_GROUP=True, adaptive_multipath)
- Commands:
  - `python3 cli.py optimize --iterations 50 --seed 42 --output optimization_result_d12.json --summary-output artifacts/summary_d12.json`
  - Resume run from best topology:
    `python3 cli.py optimize --iterations 50 --seed 42 --resume-path optimization_result_d12.json --output optimization_result_d12.json --summary-output artifacts/summary_d12.json`
- Results:
  - Initial 50 iters: `communication_time=16.7581262470146`
  - After resume 50 iters: `communication_time=16.441805533224112`
  - 4-port switch baseline time: `16.0` (still worse than switch)
- Outputs:
  - Topology: `optimization_result_d12.json`
  - Summary: `artifacts/summary_d12.json`
  - Draw.io/SVG: `artifacts/topology_d12.drawio`, `artifacts/topology_d12.svg`

### d=12 (ALLOW_INTRA_GROUP=False)
- Command:
  - `python3 cli.py optimize --iterations 50 --seed 42 --output optimization_result_d12_nointra.json --summary-output artifacts/summary_d12_nointra.json`
- Result:
  - `communication_time=18.02601868110566` (worse than switch)
- Outputs:
  - Topology: `optimization_result_d12_nointra.json`
  - Summary: `artifacts/summary_d12_nointra.json`

### d=12 (adaptive_bounded_multipath: MAX_SHORTEST_PATHS=32, EXTRA_HOPS=2, ROUTING_ITERATIONS=6)
- Command (attempted, long runtime):
  - `python3 cli.py optimize --iterations 50 --seed 42 --output optimization_result_d12_route.json --summary-output artifacts/summary_d12_route.json`
  - Also attempted segmented runs (10-iter chunks) with resume path.
- Result (only first 10-iter segment completed):
  - `communication_time=100.6334766437065` (far worse; likely unstable due to
    heavy path enumeration)
- Outputs:
  - Topology: `optimization_result_d12_route.json`
  - Summary: `artifacts/summary_d12_route.json`

## Notes on reproducibility
- Re-run any test by using the command listed above and the same seed.
- Topology edge lists are stored in the `optimization_result_*.json` files.
- Routing strategy details are stored in each summary file under `routing_config`.
- Visualization outputs are in `artifacts/` (draw.io and SVG where generated).
