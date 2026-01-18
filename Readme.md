# Network Simulator

## 🧩 Overview

This project simulates and visualizes network topologies and traffic scenarios using a discrete-event simulator (DES).
It includes lightweight demo topologies (HSH, Simple-Star) and an AI Factory topology runner.

## ⚙️ Implementation Approach
- **Language:** Python 3.9+
- **Framework:** Event-driven discrete-event simulator
- **Visualization:** matplotlib + networkx
- **Logging:** Python logging (see runner flags / YAML)

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
