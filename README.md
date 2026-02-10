# Network Simulator for AI Factory Workloads

## Project Overview

This project is a **discrete-event network simulator** designed to evaluate routing strategies for AI training workloads in data center fabrics. It focuses on comparing different load-balancing approaches (ECMP, Flowlet, Adaptive) under various traffic patterns and failure scenarios.
Project experiments summary is described in submitted project paper.
This document focus on  instructions for running simulations, analyzing results, and possibly extending the simulator for future research.

### Key Features

- **Multiple Routing Algorithms**: ECMP (Equal-Cost Multi-Path), Flowlet-based routing, and Adaptive routing
- **AI Workload Modeling**: Simulates realistic AI training patterns including:
  - DP (Data Parallel) heavy workloads with AllReduce collectives
  - Mixed workloads combining TP (Tensor Parallel) and PP+DP (Pipeline + Data Parallel)
  - Mice flow injection for latency sensitivity analysis
- **Fabric Topologies**: Clos/Leaf-Spine architectures with configurable scale
- **Failure Scenarios**: Link failure injection to test resilience
- **Performance Metrics**: Step completion time, FCT (Flow Completion Time), queue occupancy, congestion analysis

### Research Outputs

Detailed analysis and results are available in **`project.pdf`**.

---

## Project Structure

```
network_sim/
├── project.pdf                        # Main paper that describes the research and results
├── ai_factory_network_simulation.py   # Main entry point for AI factory scenarios (YAML-driven)
├── testing_scenarios.py                # Entry point for simple test scenarios (CLI-driven)
├── requirements.txt                    # Python dependencies
├── run_all_not_light.ps1              # Batch runner for heavy experiments (Windows PowerShell)
│
├── ai_factory_simulation/              # AI workload modeling
│   ├── core/                           # Core entities (jobs, workers, collectives)
│   ├── scenarios/                      # Scenario definitions and configurations
│   │   └── scenarios_configuration/    # YAML configuration files
│   │       ├── testing/                # Lightweight configs for quick tests
│   │       ├── ai_factory_su_dp_heavy_scenario_*.yaml
│   │       └── ai_factory_su_mixed_scenario_*.yaml
│   ├── traffic/                        # Traffic generators
│   └── workloads/                      # Workload definitions
│
├── network_simulation/                 # Core network simulation engine
│   ├── host.py                         # End-host nodes
│   ├── switch.py                       # Switch nodes with routing logic
│   ├── link.py                         # Network links
│   ├── port.py                         # Port queues
│   ├── packet.py                       # Packet structures
│   └── network_node.py                 # Routing mode implementations
│
├── network_simulators/                 # Topology builders
│   ├── ai_factory_su_network_simulator.py  # AI Factory Scale-Up topology
│   ├── hsh_network_simulator.py            # HSH topology (testing)
│   └── simple_star_network_simulator.py    # Star topology (testing)
│
├── des/                                # Discrete Event Simulation framework
│   └── des.py                          # Event scheduler
│
├── log_analyze_utilities/              # Post-processing and analysis
│   └── workload_comparison_plotter.py  # Graph generation from batch logs
│
├── visualization/                      # Visualization tools
│   ├── experiment_visualizer.py        # Result visualizers
│   └── visualizer.py                   # Topology visualizers
│
├── scenarios/                          # Simple test scenarios
│   ├── hsh_pingpong.py
│   ├── simple_star_all_to_all.py
│   └── none_scenario.py
│
├── unit_tests/                         # Unit tests (pytest)
│   ├── des_tests/
│   ├── network_sim_tests/
│   ├── mixed_scenario_tests/
│   └── ip_tests/
│
├── batch_logs/                         # Output logs from batch runs
└── results/                            # Output graphs and visualizations
```

---

## Installation

### Prerequisites

- **Python 3.13+**
- **System dependencies**: Graphviz (for topology visualization)
  - Windows: Download from https://graphviz.org/download/
  - Linux: `sudo apt-get install graphviz`
  - macOS: `brew install graphviz`

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/AlonZeltser/networks_for_AI_factories_and_datacenters_final_project.git
   cd network_sim
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify installation by running unit tests:
   ```bash
   python -m pytest unit_tests/ -v
   ```


#### IDE Setup (Optional)

**PyCharm:**
1. Open project: `File` → `Open` → Select `network_sim` directory
2. Configure interpreter: `File` → `Settings` → `Project: network_sim` → `Python Interpreter`
3. Click gear icon → `Add Interpreter` → Choose system Python or create virtualenv
4. Install requirements: PyCharm will prompt, or run `pip install -r requirements.txt` in terminal

**VS Code:**
1. Open project folder
2. Press `Ctrl+Shift+P` → `Python: Select Interpreter`
3. Choose your Python installation
4. Open terminal in VS Code and run `pip install -r requirements.txt`

---

## Running Simulations

### 1. Simple Test Scenarios (Quick Validation)

Use `testing_scenarios.py` for lightweight tests with simple topologies:

```bash
python testing_scenarios.py <topology> <scenario> [options]
```

**Available Topologies:**
- `hsh` - HSH basic Host-Switch-Host topology
- `simple-star` - Simple Star topology for testing routing logic

**Available Scenarios:**
- `none` - Empty scenario (topology creation only, no traffic events)
- `hsh-pingpong` - Ping-pong traffic pattern
- `simple-star-all-to-all` - All-to-all traffic

**Options:**
- `--link-failure <percent>` - Percentage of links to fail (0-100)
- `--message-verbose` - Enable detailed packet logging
- `--verbose-route` - Enable routing decision logging

**Example:**
```bash
python testing_scenarios.py hsh hsh-pingpong
python testing_scenarios.py simple-star simple-star-all-to-all --link-failure 5.0
```

**Output:**
- Console logs
- Per-run log files in project root
- Topology visualizations in `results/`

---

### 2. AI Factory Scenarios (Main Experiments)

Use `ai_factory_network_simulation.py` with YAML configuration files for comprehensive AI workload simulations.
YAML files are located in `ai_factory_simulation/scenarios/scenarios_configuration/` and define all parameters for topology, routing, workload, and run settings.

#### Command Syntax

```bash
python ai_factory_network_simulation.py <path-to-config.yaml>
```

#### Quick Test (Lightweight Configs)

For fast validation (completes in seconds):

```bash
# DP-heavy workload with ECMP routing
python ai_factory_network_simulation.py ai_factory_simulation/scenarios/scenarios_configuration/testing/ai_factory_su_dp_light_scenario_ecmp.yaml

# DP-heavy workload with Adaptive routing
python ai_factory_network_simulation.py ai_factory_simulation/scenarios/scenarios_configuration/testing/ai_factory_su_dp_light_scenario_adaptive.yaml

# Mixed workload with ECMP routing
python ai_factory_network_simulation.py ai_factory_simulation/scenarios/scenarios_configuration/testing/ai_factory_su_mixed_scenario_ecmp_light.yaml

# Mixed workload with Adaptive routing
python ai_factory_network_simulation.py ai_factory_simulation/scenarios/scenarios_configuration/testing/ai_factory_su_mixed_scenario_adaptive_light.yaml
```

#### Full Experiments (Heavy Workloads)

**Warning:** These configurations run full-scale experiments and can take **hours to complete**. They are designed for batch execution.

Located in `ai_factory_simulation/scenarios/scenarios_configuration/`:

**DP-Heavy Workload Scenarios:**
- `ai_factory_su_dp_heavy_scenario_ecmp_low.yaml` - Low load (X1)
- `ai_factory_su_dp_heavy_scenario_ecmp_mid.yaml` - Medium load (X2)
- `ai_factory_su_dp_heavy_scenario_ecmp_high.yaml` - High load (X8)
- `ai_factory_su_dp_heavy_scenario_ecmp_high_failures.yaml` - High load + 5% link failures
- Similar variants for `flowlet` and `adaptive` routing

**Mixed Workload Scenarios:**
- `ai_factory_su_mixed_scenario_ecmp_low.yaml` - Low load (X1)
- `ai_factory_su_mixed_scenario_ecmp_mid.yaml` - Medium load (X2)
- `ai_factory_su_mixed_scenario_ecmp_high.yaml` - High load (X4)
- `ai_factory_su_mixed_scenario_ecmp_high_failures.yaml` - High load + 5% link failures
- Similar variants for `flowlet` and `adaptive` routing

**Example (Heavy Run):**
```bash
python ai_factory_network_simulation.py ai_factory_simulation/scenarios/scenarios_configuration/ai_factory_su_dp_heavy_scenario_ecmp_high.yaml
```

---

### 3. Batch Execution (All Experiments)

For running multiple experiments sequentially, use the PowerShell script (Windows):

```powershell
# Run all configured scenarios
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all_not_light.ps1

# List scenarios without running
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all_not_light.ps1 -ListOnly

# Stop on first error
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_all_not_light.ps1 -StopOnError
```

**Note:** Edit the `$Scenarios` array in `run_all_not_light.ps1` to select which configurations to run.

**Output:**
- Per-scenario logs in `batch_logs/` (directory created automatically if missing)
- Summary file generated at completion

---

## YAML Configuration Structure

YAML files define all simulation parameters. Key sections:

### `run` Section
```yaml
run:
  file_debug: false          # Enable DEBUG-level file logging
  message_verbose: false     # Log individual packet events
  verbose_route: false       # Log routing decisions
  visualize: false           # Generate topology visualizations
```

### `topology` Section
```yaml
topology:
  type: ai-factory-su        # Topology type

  ai_factory_su:
    leaves: 8                        # Number of leaf switches
    spines: 4                        # Number of spine switches
    servers_per_leaf: 4              # Servers per leaf
    server_parallel_links: 8         # Links from each server to leaf
    leaf_to_spine_parallel_links: 8  # Links between each leaf-spine pair

  routing:
    mode: ecmp               # Routing: ecmp | adaptive | flowlet
    ecmp_flowlet_n_packets: 0  # Flowlet threshold (0 = disabled)

  links:
    failure_percent: 0.0     # Percentage of links to fail
    bandwidth_bps:
      server_to_leaf: 4e9    # 4 Gbps
      leaf_to_spine: 4e9

  max_path: 64               # Max ECMP paths
  mtu: 4096                  # Maximum Transmission Unit (bytes)
  ttl: 64                    # Time-to-live
```

### `scenario` Section (DP-Heavy Example)
```yaml
scenario:
  name: ai-factory-su-workload1-dp-heavy
  params:
    steps: 50                # Number of training steps
    seed: 1972               # Random seed
    num_buckets: 8           # Gradient buckets for AllReduce
    bucket_bytes_per_participant: 4194304  # 4 MiB per bucket
    gap_us: 0.0              # Inter-message gap
    t_fwd_bwd_ms: 10.0       # Forward-backward compute time
    optimizer_ms: 5.0        # Optimizer compute time

    mice:                    # Background mice flows (optional)
      enabled: true
      seed: 2026
      start_delay_s: 0.0
      end_time_s: 10.0
      interarrival_s: 0.001
      min_packets: 1
      max_packets: 4
      force_cross_rack: true
```

### `scenario` Section (Mixed Workload Example)
```yaml
scenario:
  name: ai-factory-su-mixed_scenario
  params:
    steps: 50                # Overall simulation steps
    seed: 2026
    traffic_scale: 1.0       # Traffic multiplier

    allocation_mode: rack_balanced      # Worker placement
    stage_placement_mode: topology_aware

    jobs:
      tp_heavy:
        steps: 100           # Steps for TP-heavy job
      pp_dp:
        steps: 200           # Steps for PP+DP job

    # TP-heavy job parameters
    tp_heavy_fwd_compute_ms: 5.0
    tp_heavy_micro_collectives: 16
    tp_heavy_micro_collective_bytes_per_participant: 524288
    # ... (see example YAML for full parameters)

    # PP+DP job parameters
    pp_dp_microbatch_count: 4
    pp_dp_activation_bytes_per_microbatch: 1048576
    # ... (see example YAML for full parameters)

    mice:
      enabled: true
      # ... (same as DP-heavy)
```

---

## Analyzing Results

### Log Files

Each run generates a detailed log file containing:
- Topology summary (node/link counts)
- Parameter summary (configuration)
- Run statistics:
  - Step completion times (mean, p95, p99)
  - Mice flow FCT statistics
  - Queue occupancy metrics
  - Total simulation time

**Locations:**
- Simple scenarios: `{topology}.{scenario}_YYYYMMDD_HHMMSS.log`
- AI Factory scenarios: `batch_logs/run_ai_factory_simulation_..._.log`

### Generating Comparison Graphs

After running multiple experiments, generate comparison plots:

```bash
python log_analyze_utilities/workload_comparison_plotter.py
```

**Generated Graphs** (saved to `results/`):

1. **Step Time Comparisons**
   - `heavy_workload_step_time_comparison.png`
   - `mixed_workload_step_time_comparison.png`
   - Shows mean and p95 step times across load points and routing methods

2. **Job Total Time**
   - `heavy_workload_job_time_comparison.png`
   - `mixed_workload_job_time_comparison.png`
   - Total simulation time per configuration

3. **Step Completion CDFs**
   - `heavy_workload_step_cdf.png`
   - `mixed_workload_step_cdf.png`
   - Progress of step completion over time

4. **Mice FCT Analysis**
   - `heavy_workload_mice_fct_vs_load.png`
   - `mixed_workload_mice_fct_vs_load.png`
   - Small flow latency under different loads

5. **Queue Occupancy**
   - `queue_global_peak_vs_load.png`
   - `avg_switch_peak_queue_vs_load.png`
   - Congestion metrics across experiments

**Prerequisites:** Must have batch logs from completed runs in `batch_logs/` directory.

---

## Running Unit Tests

The project includes comprehensive unit tests for core components:

```bash
# Run all tests
python -m pytest unit_tests/ -v

# Run specific test suites
python -m pytest unit_tests/des_tests/ -v
python -m pytest unit_tests/network_sim_tests/ -v
python -m pytest unit_tests/mixed_scenario_tests/ -v
python -m pytest unit_tests/ip_tests/ -v
```

**Test Coverage:**
- DES (Discrete Event Simulation) framework
- Network primitives (ports, queues, routing)
- IP address parsing and prefix matching
- Scenario execution and determinism

---

## Key Concepts

### Routing Modes

1. **ECMP (Equal-Cost Multi-Path)**
   - Hash-based path selection
   - Deterministic per-flow routing
   - Standard baseline

2. **Flowlet**
   - Flow-based routing with periodic re-routing
   - Configurable flowlet threshold (`ecmp_flowlet_n_packets`)
   - Balances persistence and adaptability

3. **Adaptive**
   - Queue-aware routing
   - Selects path with shortest egress queue among ECMP candidates
   - Reacts to congestion in real-time

### Workload Types

1. **DP-Heavy**
   - Single data-parallel job
   - AllReduce collectives across all workers
   - Highly synchronized, bandwidth-intensive

2. **Mixed**
   - Two concurrent jobs:
     - **TP-Heavy**: Tensor parallel with many micro-collectives
     - **PP+DP**: Pipeline parallel with data parallel synchronization
   - Diverse message sizes and patterns
   - Tests routing under heterogeneous traffic

### Mice Flows

- Background short flows injected during training
- Used to measure latency sensitivity under load
- Configurable arrival rate, size distribution, cross-rack enforcement

---

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python version: `python --version` (requires 3.8+)

2. **Graphviz Errors**
   - Install system Graphviz: https://graphviz.org/download/
   - Add Graphviz to system PATH

3. **Out of Memory (Heavy Runs)**
   - Heavy scenarios are memory-intensive
   - Use light configs for testing: `*_light.yaml`
   - Close other applications during batch runs

4. **Slow Execution**
   - Disable visualization: Set `visualize: false` in YAML
   - Reduce verbosity: Set `message_verbose: false`, `verbose_route: false`
   - Use light configs for validation

### Debug Options

Enable detailed logging in YAML:
```yaml
run:
  file_debug: true           # Full DEBUG logs to file
  message_verbose: true      # Log every packet
  verbose_route: true        # Log routing decisions
```

---

## Development

### Code Style

- Python 3.8+ type hints throughout
- Modular design with clear separation of concerns
- Discrete event simulation paradigm (event-driven)

### Adding New Scenarios

1. Create scenario class in `scenarios/` or `ai_factory_simulation/scenarios/`
2. Implement required methods: `setup()`, `run_step()`
3. Register scenario name in entry point (`ai_factory_network_simulation.py`)
4. Create YAML configuration in `scenarios_configuration/`

### Adding New Routing Algorithms

1. Add new `RoutingMode` enum value in `network_simulation/network_node.py`
2. Implement routing logic in `Switch.route_packet()`
3. Update YAML parser in `ai_factory_network_simulation.py`

---

## Performance Characteristics

### Light Configs
- **Steps**: 1-5
- **Runtime**: Seconds to minutes
- **Purpose**: Validation, debugging, quick tests

### Heavy Configs
- **Steps**: 50-200
- **Runtime**: Hours per scenario
- **Purpose**: Full experimental results

### Batch Runs (All Scenarios)
- **Count**: 24+ scenarios (6 routing × 4 load points × 2 workload types)
- **Total Runtime**: Many hours to days
- **Purpose**: Complete comparison study

---

## Citation

If you use this simulator in your research, please cite the accompanying paper:

```bibtex
@techreport{zeltser2026network,
  title={Network Simulator for AI Factory Workloads: Evaluating Routing Strategies in Data Center Fabrics},
  author={Zeltser},
  institution={Ben-Gurion University of the Negev},
  year={2026},
  month={February},
  note={Available in project.pdf}
}
```

For more details, see **`project.pdf`**.

---

## License

This project is available for academic and educational purposes. 

**Academic Use:** Free to use for research and educational purposes with proper citation.

**Commercial Use:** Please contact the authors for licensing terms.

Copyright © 2026 Alon Zeltser. All rights reserved.

---

## Contact

For questions, bug reports, or collaboration inquiries, please contact:

- **Alon Zeltser**: [alonzeltser1@gmail.com](mailto:alonzeltser1@gmail.com)

**Institution:** Ben-Gurion University of the Negev, Department of Computer Science

---

## Acknowledgments

This simulator was developed for studying load-balancing strategies in AI training fabrics, with focus on comparing traditional (ECMP), flow-aware (Flowlet), and congestion-aware (Adaptive) routing approaches.

---

**Last Updated**: February 2026
