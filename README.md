# Topology Optimization Toolkit

This project optimizes direct-chip interconnect topologies to minimize the max communication time
for a fixed a→b traffic pattern (all sources in group A sending to all destinations in group B).

## What the code does

* **`traffic.py`** builds the a→b traffic matrix and demand list.
* **`topology.py`** represents the topology graph and implements rewiring moves.
* **`simulate.py`** routes traffic (with multipath strategies) and estimates communication time;
  relay selection only matters when a source has multiple targets (e.g., MoE traffic).
  It also supports async timing (Poisson start times) with time-evolving link loads and
  reports mean/variance of per-request completion times.
* **`optimize.py`** searches for better topologies using simulated annealing + rewires/swaps,
  with optional resume and early stopping.
* **`baseline.py`** computes the equivalent switch baseline for comparison; for MoE
  traffic it assumes each source sends one shared payload (multicast at the switch).
* **`visualize_history.py`** plots the iteration vs communication-time curve (if matplotlib exists).
* **`visualize_topology.py`** draws the topology graph (if matplotlib + networkx exist).
* **`export_drawio_svg.py`** exports draw.io and SVG diagrams for the optimized topology.
* **`cli.py`** wraps everything in a CLI workflow.

## Requirements

Install Python 3.10+ and the packages listed in `requirements.txt`.

## Usage

Generate the traffic file:
```bash
python cli.py generate-traffic --output traffic.json
```

Run optimization:
```bash
python cli.py optimize --iterations 1500 --seed 42 --output optimization_result.json \
  --history-plot artifacts/optimization_history.png \
  --topology-plot artifacts/topology.png \
  --drawio-output artifacts/topology.drawio \
  --svg-output artifacts/topology.svg
```

Resume from a previous topology (saved `edges` list JSON):
```bash
python cli.py optimize --iterations 1500 --seed 42 \
  --resume-path optimization_result.json \
  --output optimization_result.json
```

Simulate the initial topology:
```bash
python cli.py simulate --seed 42
```

Simulate with async timing:
```bash
python cli.py simulate --seed 42 --timing-model async
```

Async-optimized routing (relay + multipath, async-aware):
```bash
python cli.py simulate --seed 42 --timing-model async --routing-strategy async_optimized
```

Export the initial topology to JSON:
```bash
python cli.py export --seed 42 --output topology.json
```

Visualize the initial topology (requires matplotlib + networkx):
```bash
python cli.py visualize --seed 42 --output artifacts/initial_topology.png
```

Compare with switch baseline:
```bash
python cli.py compare-switch --iterations 500 --seed 42
```

## Output fields (optimize)

The `optimize` command prints a JSON payload containing:
- `best_result` (communication time, max edge load, disconnected flows)
- `switch_baseline` (equivalent switch ports/chip and time)
- `traffic_matrix` (a→b communication matrix)
- `port_utilization` (per-chip utilization ratios)
- `history_times` and `history_plot` (iteration curve)
- `topology_plot`, `drawio_path`, `svg_path` (topology visualization exports)
