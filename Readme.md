# Network Simulator

## 🧩 Overview

This project simulates and visualizes network topologies and traffic scenarios using a discrete-event simulator (DES).
It includes lightweight demo topologies (HSH, Simple-Star) and an AI Factory topology runner.

## ⚙️ Implementation Approach
- **Language:** Python 3.9+
- **Framework:** Event-driven discrete-event simulator
- **Visualization:** matplotlib + networkx
- **Logging:** Python logging (console)

## Project structure

```
network_sim/
├── Readme.md
├── requirements.txt
├── testing_scenarios.py
├── ai_factory_simulation/
│   ├── __init__.py
│   ├── main.py
│   └── docs/
│       └── example_config.yaml
├── network_simulation/
├── network_simulators/
├── scenarios/
├── visualization/
└── unit_tests/
```

## Running

### 1) AI Factory simulation (YAML-driven)

The recommended entrypoint for AI Factory simulations is the YAML-driven runner:

- Script/module: `ai_factory_simulation/main.py`
- CLI: takes only one argument: the path to a YAML config

Example:

python ai_factory_network_simulation.py ai_factory_simulation/scenarios/example_config.yaml

### 1b) Batch running multiple AI-factory configs (Windows / PowerShell)

For repeatable experiment batches on Windows, use:

- Script: `scripts/run_ai_factory_batch.ps1`

It runs `ai_factory_network_simulation.py` for each YAML config you list.

Example:

```powershell
# From repo root
powershell -ExecutionPolicy Bypass -File .\scripts\run_ai_factory_batch.ps1 -Configs @(
  "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_ecmp.yaml",
  "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_adaptive.yaml"
)

# Continue even if some configs fail
powershell -ExecutionPolicy Bypass -File .\scripts\run_ai_factory_batch.ps1 -ContinueOnError -Configs @(
  "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_ecmp.yaml",
  "ai_factory_simulation\scenarios\ai_factory_su_dp_heavy_scenario_adaptive.yaml"
)
```

Each run already produces a per-run logfile via `log_setup.configure_run_logging()`.

#### JetBrains tip

If you prefer click-to-run, create a **Run/Debug configuration** for PowerShell that runs:

- Script: `scripts/run_ai_factory_batch.ps1`
- Parameters: `-Configs @(...)`

This makes it easy to re-run the same experiment batch.

#### YAML configuration schema (high level)

The YAML is grouped by subject:

- `run`: debug/verbosity/visualization toggles
- `topology`: AI-factory topology parameters (type, max_path, link failures, etc.)
- `scenario`: scenario selection + parameters (steps, buckets, bytes per send, etc.)

See `ai_factory_simulation/scenarios/example_config.yaml` for a concrete example.

### 2) Quick testing runner (HSH / Simple-Star)

For fast manual testing and debugging of the basic demo topologies:

- Script: `testing_scenarios.py`
- CLI: `topology` + `scenario`

Example:

python testing_scenarios.py hsh hsh-pingpong
python testing_scenarios.py simple-star simple-star-all-to-all

## AI Factory (YAML runner)

The AI Factory runner is configured via YAML (`ai_factory_network_simulation.py`).
Bucket-related knobs live under `scenario.params`:

- `num_buckets`
- `bucket_bytes_per_participant`

See `ai_factory_simulation/scenarios/example_config.yaml` for a complete example.
