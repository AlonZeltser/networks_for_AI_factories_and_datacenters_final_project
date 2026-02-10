"""
Workload Comparison Plotter

This script creates comparison graphs from batch logs showing performance
across different traffic scales and routing methods.

For heavy workload: X-axis is X1, X2, X8, X8-failure (low-mid-high-high_failures)
For mixed workload: X-axis is X1, X2, X4, X4-failure (low-mid-high-high_failures)

Y-axis: Mean step time and P95 step time
Lines: 3 solid lines (ECMP, Flowlet, Adaptive) for mean, 3 dashed lines for P95
Uses colorblind-friendly markers and colors.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import numpy as np


# Paths
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BATCH_LOGS_DIR = os.path.join(ROOT, "batch_logs")
RESULTS_DIR = os.path.join(ROOT, "results")


# Colorblind-friendly colors and markers
COLORS = {
    'ecmp': '#0173B2',      # Blue
    'flowlet': '#DE8F05',   # Orange
    'adaptive': '#029E73'   # Green
}

MARKERS = {
    'ecmp': 'o',      # Circle
    'flowlet': 's',   # Square
    'adaptive': '^'   # Triangle
}


@dataclass
class StepTimeData:
    """Step time statistics for a run."""
    mean: float
    p95: float
    routing_method: str
    workload_type: str  # 'heavy' or 'mixed'
    scale_label: str    # 'low', 'mid', 'high', 'high_failures'
    job_total_time: float = 0.0  # Total job time in seconds
    step_durations: List[float] = field(default_factory=list)  # Individual step durations in ms
    mice_fct_avg_ms: float = 0.0  # Mice FCT average in ms
    mice_fct_p95_ms: float = 0.0  # Mice FCT p95 in ms
    mice_flows: int = 0  # Number of mice flows
    global_max_port_peak_queue_len: float = 0.0  # Global max queue length in packets
    avg_node_peak_egress_queue_len: float = 0.0  # Average switch peak queue in packets


def parse_log_file(filepath: str) -> Optional[StepTimeData]:
    """
    Parse a batch log file to extract step time statistics.

    Returns StepTimeData or None if parsing fails.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract filename to determine parameters
    filename = os.path.basename(filepath)

    # Determine workload type
    if '_dp_heavy_scenario_' in filename:
        workload_type = 'heavy'
    elif '_mixed_scenario_' in filename:
        workload_type = 'mixed'
    else:
        return None

    # Determine routing method
    if '_ecmp_' in filename:
        routing_method = 'ecmp'
    elif '_flowlet_' in filename:
        routing_method = 'flowlet'
    elif '_adaptive_' in filename:
        routing_method = 'adaptive'
    else:
        return None

    # Determine scale
    if '_low.yaml_' in filename or '_low_failures.yaml_' in filename:
        scale_label = 'low'
    elif '_mid.yaml_' in filename or '_mid_failures.yaml_' in filename:
        scale_label = 'mid'
    elif '_high.yaml_' in filename:
        scale_label = 'high'
    elif '_high_failures.yaml_' in filename:
        scale_label = 'high_failures'
    else:
        return None

    # Extract step time statistics from the log
    # Pattern: ai_factory_step_time_ms_per_job: {'job': {'step_time_avg_ms': X, 'step_time_p95_ms': Y, ...}}
    # Or for mixed: {'tp_heavy': {...}, 'pp_dp': {...}}

    pattern = r"ai_factory_step_time_ms_per_job:\s*(\{.+?\})\s*(?:mice_flows|$)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print(f"Warning: Could not find step time data in {filename}")
        return None

    data_str = match.group(1)

    # Parse the dictionary string
    try:
        # Safe eval with restricted namespace
        data_dict = eval(data_str, {"__builtins__": {}}, {})

        # Initialize variables
        mean = 0.0
        p95 = 0.0

        # For heavy workload, there's only one job
        if workload_type == 'heavy':
            if 'job' in data_dict:
                job_data = data_dict['job']
                mean = job_data.get('step_time_avg_ms', 0.0)
                p95 = job_data.get('step_time_p95_ms', 0.0)
            else:
                print(f"Warning: Unexpected job format in {filename}", flush=True)
                return None

        # For mixed workload, average across tp_heavy and pp_dp
        elif workload_type == 'mixed':
            if 'tp_heavy' in data_dict and 'pp_dp' in data_dict:
                tp_mean = data_dict['tp_heavy'].get('step_time_avg_ms', 0.0)
                tp_p95 = data_dict['tp_heavy'].get('step_time_p95_ms', 0.0)
                pp_mean = data_dict['pp_dp'].get('step_time_avg_ms', 0.0)
                pp_p95 = data_dict['pp_dp'].get('step_time_p95_ms', 0.0)

                # Average the two workloads
                mean = (tp_mean + pp_mean) / 2.0
                p95 = (tp_p95 + pp_p95) / 2.0
            else:
                print(f"Warning: Unexpected job format in {filename}", flush=True)
                return None

        # Extract job total time (simulator time)
        job_total_time = 0.0
        runtime_match = re.search(r'total run time \(simulator time in seconds\):\s*([0-9.]+)', content)
        if runtime_match:
            job_total_time = float(runtime_match.group(1))

        # Extract individual step durations from log timestamps
        step_durations = []
        step_start_pattern = r'\[sim_t=([0-9.]+)s\] Step starting\s+step=(\d+)'
        step_finish_pattern = r'\[sim_t=([0-9.]+)s\] Step finished\s+step=(\d+)'

        step_starts = {}
        for match in re.finditer(step_start_pattern, content):
            sim_time = float(match.group(1))
            step_num = int(match.group(2))
            step_starts[step_num] = sim_time

        for match in re.finditer(step_finish_pattern, content):
            sim_time = float(match.group(1))
            step_num = int(match.group(2))
            if step_num in step_starts:
                duration_s = sim_time - step_starts[step_num]
                duration_ms = duration_s * 1000.0  # Convert to milliseconds
                step_durations.append(duration_ms)

        # Extract mice FCT statistics
        mice_fct_avg_ms = 0.0
        mice_fct_p95_ms = 0.0
        mice_flows = 0

        mice_avg_match = re.search(r'mice_fct_avg_ms:\s*([0-9.]+)', content)
        if mice_avg_match:
            mice_fct_avg_ms = float(mice_avg_match.group(1))

        mice_p95_match = re.search(r'mice_fct_p95_ms:\s*([0-9.]+)', content)
        if mice_p95_match:
            mice_fct_p95_ms = float(mice_p95_match.group(1))

        mice_flows_match = re.search(r'mice_flows:\s*(\d+)', content)
        if mice_flows_match:
            mice_flows = int(mice_flows_match.group(1))

        # Extract queue occupancy statistics
        global_max_queue = 0.0
        avg_switch_peak_queue = 0.0

        global_queue_match = re.search(r'global_max_port_peak_queue_len \(packets\):\s*([0-9.]+)', content)
        if global_queue_match:
            global_max_queue = float(global_queue_match.group(1))

        avg_queue_match = re.search(r'avg_node_peak_egress_queue_len \(packets\):\s*([0-9.]+)', content)
        if avg_queue_match:
            avg_switch_peak_queue = float(avg_queue_match.group(1))

        return StepTimeData(
            mean=mean,
            p95=p95,
            routing_method=routing_method,
            workload_type=workload_type,
            scale_label=scale_label,
            job_total_time=job_total_time,
            step_durations=step_durations,
            mice_fct_avg_ms=mice_fct_avg_ms,
            mice_fct_p95_ms=mice_fct_p95_ms,
            mice_flows=mice_flows,
            global_max_port_peak_queue_len=global_max_queue,
            avg_node_peak_egress_queue_len=avg_switch_peak_queue
        )

    except Exception as e:
        print(f"Error parsing data from {filename}: {e}", flush=True)
        return None


def collect_all_data() -> List[StepTimeData]:
    """Collect data from all log files in batch_logs directory."""
    all_data = []

    if not os.path.exists(BATCH_LOGS_DIR):
        print(f"Error: Batch logs directory not found: {BATCH_LOGS_DIR}")
        return all_data

    for filename in os.listdir(BATCH_LOGS_DIR):
        if not filename.endswith('.log'):
            continue

        if filename == 'summary_20260128_142250.txt':
            continue

        filepath = os.path.join(BATCH_LOGS_DIR, filename)
        data = parse_log_file(filepath)

        if data:
            all_data.append(data)

    return all_data


def create_workload_graph(data: List[StepTimeData], workload_type: str, output_filename: str):
    """
    Create a graph for a specific workload type.

    Args:
        data: List of StepTimeData objects
        workload_type: 'heavy' or 'mixed'
        output_filename: Name of output PNG file
    """
    # Filter data for this workload type
    workload_data = [d for d in data if d.workload_type == workload_type]

    if not workload_data:
        print(f"Warning: No data found for {workload_type} workload")
        return

    # Define X-axis labels based on workload type
    if workload_type == 'heavy':
        x_labels = ['X1', 'X2', 'X8', 'X8-failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Heavy Workload: Step Time Comparison'
    else:  # mixed
        x_labels = ['X1', 'X2', 'X4', 'X4-failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Mixed Workload: Step Time Comparison'

    # Organize data by routing method and scale
    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    # Initialize data structures
    means = {method: [] for method in routing_methods}
    p95s = {method: [] for method in routing_methods}

    # Collect data points in the correct order
    for scale in scale_order:
        for method in routing_methods:
            # Find matching data point
            matching = [d for d in workload_data
                       if d.routing_method == method and d.scale_label == scale]

            if matching:
                means[method].append(matching[0].mean)
                p95s[method].append(matching[0].p95)
            else:
                # No data point found
                means[method].append(None)
                p95s[method].append(None)

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 8))

    x_positions = np.arange(len(x_labels))

    # Plot lines for each routing method
    for method in routing_methods:
        color = COLORS[method]
        marker = MARKERS[method]
        label = method.upper()

        # Filter out None values for plotting
        mean_values = means[method]
        p95_values = p95s[method]

        # Mean (solid line)
        valid_mean_x = [x for x, v in zip(x_positions, mean_values) if v is not None]
        valid_mean_y = [v for v in mean_values if v is not None]

        if valid_mean_x:
            ax.plot(valid_mean_x, valid_mean_y,
                   color=color, marker=marker, linewidth=2,
                   markersize=8, label=f'{label} Mean',
                   linestyle='-')

        # P95 (dashed line)
        valid_p95_x = [x for x, v in zip(x_positions, p95_values) if v is not None]
        valid_p95_y = [v for v in p95_values if v is not None]

        if valid_p95_x:
            ax.plot(valid_p95_x, valid_p95_y,
                   color=color, marker=marker, linewidth=2,
                   markersize=8, label=f'{label} P95',
                   linestyle='--')

    # Formatting
    ax.set_xlabel('Traffic Scale', fontsize=12, fontweight='bold')
    ax.set_ylabel('Step Time (ms)', fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add some padding to y-axis
    ax.margins(y=0.1)

    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def create_job_time_graph(data: List[StepTimeData], workload_type: str, output_filename: str):
    """
    Create a graph showing total job time for a specific workload type.

    Args:
        data: List of StepTimeData objects
        workload_type: 'heavy' or 'mixed'
        output_filename: Name of output PNG file
    """
    # Filter data for this workload type
    workload_data = [d for d in data if d.workload_type == workload_type]

    if not workload_data:
        print(f"Warning: No data found for {workload_type} workload", flush=True)
        return

    # Define X-axis labels based on workload type
    if workload_type == 'heavy':
        x_labels = ['X1', 'X2', 'X8', 'X8-failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Heavy Workload: Total Job Time Comparison'
    else:  # mixed
        x_labels = ['X1', 'X2', 'X4', 'X4-failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Mixed Workload: Total Job Time Comparison'

    # Organize data by routing method and scale
    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    # Initialize data structures
    job_times = {method: [] for method in routing_methods}

    # Collect data points in the correct order
    for scale in scale_order:
        for method in routing_methods:
            # Find matching data point
            matching = [d for d in workload_data
                       if d.routing_method == method and d.scale_label == scale]

            if matching:
                job_times[method].append(matching[0].job_total_time)
            else:
                # No data point found
                job_times[method].append(None)

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 8))

    x_positions = np.arange(len(x_labels))

    # Plot lines for each routing method
    for method in routing_methods:
        color = COLORS[method]
        marker = MARKERS[method]
        label = method.upper()

        # Filter out None values for plotting
        time_values = job_times[method]

        valid_x = [x for x, v in zip(x_positions, time_values) if v is not None]
        valid_y = [v for v in time_values if v is not None]

        if valid_x:
            ax.plot(valid_x, valid_y,
                   color=color, marker=marker, linewidth=2,
                   markersize=8, label=label,
                   linestyle='-')

    # Formatting
    ax.set_xlabel('Traffic Scale', fontsize=12, fontweight='bold')
    ax.set_ylabel('Job Total Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add some padding to y-axis
    ax.margins(y=0.1)

    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def create_step_cdf_graph(data: List[StepTimeData], workload_type: str, output_filename: str):
    """
    Create a CDF graph of step durations for a specific workload type.

    Args:
        data: List of StepTimeData objects
        workload_type: 'heavy' or 'mixed'
        output_filename: Name of output PNG file
    """
    # Filter data for this workload type
    workload_data = [d for d in data if d.workload_type == workload_type]

    if not workload_data:
        print(f"Warning: No data found for {workload_type} workload", flush=True)
        return

    # Define scale order based on workload type
    if workload_type == 'heavy':
        scale_order = ['low', 'mid', 'high', 'high_failures']
        scale_labels = ['X1', 'X2', 'X8', 'X8-failure']
        title_prefix = 'Heavy Workload'
    else:  # mixed
        scale_order = ['low', 'mid', 'high', 'high_failures']
        scale_labels = ['X1', 'X2', 'X4', 'X4-failure']
        title_prefix = 'Mixed Workload'

    # Create one subplot for each scale
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    for idx, (scale, scale_label) in enumerate(zip(scale_order, scale_labels)):
        ax = axes[idx]

        # Plot CDF for each routing method at this scale
        # Changed to show progress over time: X-axis = step index, Y-axis = CDF
        for method in routing_methods:
            # Find matching data point
            matching = [d for d in workload_data
                       if d.routing_method == method and d.scale_label == scale]

            if matching and matching[0].step_durations:
                durations = matching[0].step_durations  # Keep original order (time sequence)
                n = len(durations)

                # Calculate cumulative time as steps complete
                cumulative_time = np.cumsum(durations)

                # CDF: fraction of steps completed at each point in time
                # Prepend 0 at time 0 (no steps completed yet)
                x_time = np.concatenate([[0], cumulative_time])
                y_cdf = np.concatenate([[0], np.arange(1, n + 1) / n])

                color = COLORS[method]
                marker = MARKERS[method]
                label = method.upper()

                ax.plot(x_time, y_cdf,
                       color=color, linewidth=2,
                       marker=marker, markersize=6, markevery=max(1, (n + 1) // 10),
                       label=label)

        # Formatting for this subplot
        ax.set_xlabel('Cumulative Time (ms)', fontsize=11, fontweight='bold')
        ax.set_ylabel('Fraction of Steps Completed', fontsize=11, fontweight='bold')
        ax.set_title(f'{title_prefix}: {scale_label}', fontsize=12, fontweight='bold')
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(left=0)

    plt.suptitle(f'{title_prefix}: Step Completion Progress Over Time', fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def create_mice_fct_graph(data: List[StepTimeData], workload_type: str, output_filename: str):
    """
    Create a mice FCT vs load graph for a specific workload type.

    Shows mean and p95 mice FCT for each routing method at different load points.

    Args:
        data: List of StepTimeData objects
        workload_type: 'heavy' or 'mixed'
        output_filename: Name of output PNG file
    """
    # Filter data for this workload type
    workload_data = [d for d in data if d.workload_type == workload_type]

    if not workload_data:
        print(f"Warning: No data found for {workload_type} workload", flush=True)
        return

    # Define X-axis labels based on workload type
    if workload_type == 'heavy':
        x_labels = ['X1', 'X2', 'X8', 'X8_with_5pct_failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Heavy Workload: Mice FCT vs Load'
    else:  # mixed
        x_labels = ['X1', 'X2', 'X4', 'X4_with_5pct_failure']
        scale_order = ['low', 'mid', 'high', 'high_failures']
        title = 'Mixed Workload: Mice FCT vs Load'

    # Organize data by routing method and scale
    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    # Initialize data structures
    fct_means = {method: [] for method in routing_methods}
    fct_p95s = {method: [] for method in routing_methods}

    # Collect data points in the correct order
    for scale in scale_order:
        for method in routing_methods:
            # Find matching data point
            matching = [d for d in workload_data
                       if d.routing_method == method and d.scale_label == scale]

            if matching and matching[0].mice_flows > 0:
                fct_means[method].append(matching[0].mice_fct_avg_ms)
                fct_p95s[method].append(matching[0].mice_fct_p95_ms)
            else:
                # No data point found or no mice flows
                fct_means[method].append(None)
                fct_p95s[method].append(None)

    # Create the plot
    fig, ax = plt.subplots(figsize=(12, 8))

    x_positions = np.arange(len(x_labels))

    # Plot lines for each routing method
    for method in routing_methods:
        color = COLORS[method]
        marker = MARKERS[method]
        label = method.upper()

        # Mean FCT (solid line)
        mean_values = fct_means[method]
        valid_mean_x = [x for x, v in zip(x_positions, mean_values) if v is not None]
        valid_mean_y = [v for v in mean_values if v is not None]

        if valid_mean_x:
            ax.plot(valid_mean_x, valid_mean_y,
                   color=color, marker=marker, linewidth=2,
                   markersize=8, label=f'{label} Mean',
                   linestyle='-')

        # P95 FCT (dashed line)
        p95_values = fct_p95s[method]
        valid_p95_x = [x for x, v in zip(x_positions, p95_values) if v is not None]
        valid_p95_y = [v for v in p95_values if v is not None]

        if valid_p95_x:
            ax.plot(valid_p95_x, valid_p95_y,
                   color=color, marker=marker, linewidth=2,
                   markersize=8, label=f'{label} P95',
                   linestyle='--')

    # Formatting
    ax.set_xlabel('Offered Load Multiplier', fontsize=12, fontweight='bold')
    ax.set_ylabel('Mice FCT (ms)', fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.legend(loc='best', fontsize=10, ncol=2)
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add some padding to y-axis
    ax.margins(y=0.1)

    # Check if log scale is needed (p95 > 10x mean)
    all_means = [v for values in fct_means.values() for v in values if v is not None]
    all_p95s = [v for values in fct_p95s.values() for v in values if v is not None]

    if all_means and all_p95s:
        max_p95 = max(all_p95s)
        avg_mean = sum(all_means) / len(all_means)
        if max_p95 > 10 * avg_mean:
            ax.set_yscale('log')
            ax.set_ylabel('Mice FCT (ms) [log scale]', fontsize=12, fontweight='bold')

    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def create_queue_global_peak_graph(data: List[StepTimeData], output_filename: str):
    """
    Create a two-panel graph showing global peak queue vs load for mixed and heavy workloads.

    Figure A1: Global peak queue vs load (worst port in the whole fabric).

    Args:
        data: List of StepTimeData objects
        output_filename: Name of output PNG file
    """
    # Create two-panel figure
    fig, (ax_mixed, ax_heavy) = plt.subplots(1, 2, figsize=(16, 6))

    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    # Process each workload type
    for workload_type, ax in [('mixed', ax_mixed), ('heavy', ax_heavy)]:
        workload_data = [d for d in data if d.workload_type == workload_type]

        if not workload_data:
            continue

        # Define scale order
        if workload_type == 'heavy':
            x_labels = ['X1', 'X2', 'X8', 'X8_fail5']
            scale_order = ['low', 'mid', 'high', 'high_failures']
            title = 'Heavy Workload'
        else:  # mixed
            x_labels = ['X1', 'X2', 'X4', 'X4_fail5']
            scale_order = ['low', 'mid', 'high', 'high_failures']
            title = 'Mixed Workload'

        x_positions = np.arange(len(x_labels))

        # Plot each routing method
        for method in routing_methods:
            color = COLORS[method]
            marker = MARKERS[method]
            label = method.upper()

            values = []
            for scale in scale_order:
                matching = [d for d in workload_data
                           if d.routing_method == method and d.scale_label == scale]
                if matching:
                    values.append(matching[0].global_max_port_peak_queue_len)
                else:
                    values.append(None)

            # Plot (only mean line since we have single runs)
            valid_x = [x for x, v in zip(x_positions, values) if v is not None]
            valid_y = [v for v in values if v is not None]

            if valid_x:
                ax.plot(valid_x, valid_y,
                       color=color, marker=marker, linewidth=2,
                       markersize=8, label=label,
                       linestyle='-')

        # Formatting
        ax.set_xlabel('Offered Load Multiplier', fontsize=11, fontweight='bold')
        ax.set_ylabel('Global Peak Queue (packets)', fontsize=11, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels)
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.margins(y=0.1)

    plt.suptitle('Global Peak Queue vs Load (Worst Port in Fabric)\nLast point shows X4/X8 with 5% link failures',
                 fontsize=13, fontweight='bold')
    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def create_avg_switch_peak_queue_graph(data: List[StepTimeData], output_filename: str):
    """
    Create a two-panel graph showing average switch peak queue vs load.

    Figure A2: Average switch peak queue vs load (how widespread congestion is).

    Args:
        data: List of StepTimeData objects
        output_filename: Name of output PNG file
    """
    # Create two-panel figure
    fig, (ax_mixed, ax_heavy) = plt.subplots(1, 2, figsize=(16, 6))

    routing_methods = ['ecmp', 'flowlet', 'adaptive']

    # Process each workload type
    for workload_type, ax in [('mixed', ax_mixed), ('heavy', ax_heavy)]:
        workload_data = [d for d in data if d.workload_type == workload_type]

        if not workload_data:
            continue

        # Define scale order
        if workload_type == 'heavy':
            x_labels = ['X1', 'X2', 'X8', 'X8_fail5']
            scale_order = ['low', 'mid', 'high', 'high_failures']
            title = 'Heavy Workload'
        else:  # mixed
            x_labels = ['X1', 'X2', 'X4', 'X4_fail5']
            scale_order = ['low', 'mid', 'high', 'high_failures']
            title = 'Mixed Workload'

        x_positions = np.arange(len(x_labels))

        # Plot each routing method
        for method in routing_methods:
            color = COLORS[method]
            marker = MARKERS[method]
            label = method.upper()

            values = []
            for scale in scale_order:
                matching = [d for d in workload_data
                           if d.routing_method == method and d.scale_label == scale]
                if matching:
                    values.append(matching[0].avg_node_peak_egress_queue_len)
                else:
                    values.append(None)

            # Plot (only mean line since we have single runs)
            valid_x = [x for x, v in zip(x_positions, values) if v is not None]
            valid_y = [v for v in values if v is not None]

            if valid_x:
                ax.plot(valid_x, valid_y,
                       color=color, marker=marker, linewidth=2,
                       markersize=8, label=label,
                       linestyle='-')

        # Formatting
        ax.set_xlabel('Offered Load Multiplier', fontsize=11, fontweight='bold')
        ax.set_ylabel('Avg Switch Peak Queue (packets)', fontsize=11, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels)
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.margins(y=0.1)

    plt.suptitle('Average Switch Peak Queue vs Load (Congestion Spread)\nLast point shows X4/X8 with 5% link failures',
                 fontsize=13, fontweight='bold')
    plt.tight_layout()

    # Save the figure
    output_path = os.path.join(RESULTS_DIR, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Graph saved: {output_path}", flush=True)


def main():
    """Main function to generate all graphs."""
    import sys
    sys.stdout.reconfigure(line_buffering=True)

    print("Workload Comparison Plotter", flush=True)
    print("=" * 60, flush=True)

    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Collect all data
    print("\nCollecting data from batch logs...", flush=True)
    all_data = collect_all_data()

    if not all_data:
        print("Error: No data collected from logs", flush=True)
        return

    print(f"Collected {len(all_data)} data points", flush=True)

    # Print summary of collected data
    print("\nData summary:", flush=True)
    for workload_type in ['heavy', 'mixed']:
        workload_count = len([d for d in all_data if d.workload_type == workload_type])
        print(f"  {workload_type.capitalize()}: {workload_count} data points", flush=True)

    # Create graphs
    print("\nGenerating graphs...", flush=True)

    # Step time comparison graphs
    create_workload_graph(all_data, 'heavy', 'heavy_workload_step_time_comparison.png')
    create_workload_graph(all_data, 'mixed', 'mixed_workload_step_time_comparison.png')

    # Job time comparison graphs
    create_job_time_graph(all_data, 'heavy', 'heavy_workload_job_time_comparison.png')
    create_job_time_graph(all_data, 'mixed', 'mixed_workload_job_time_comparison.png')

    # Step duration CDF graphs
    create_step_cdf_graph(all_data, 'heavy', 'heavy_workload_step_cdf.png')
    create_step_cdf_graph(all_data, 'mixed', 'mixed_workload_step_cdf.png')

    # Mice FCT vs load graphs
    create_mice_fct_graph(all_data, 'heavy', 'heavy_workload_mice_fct_vs_load.png')
    create_mice_fct_graph(all_data, 'mixed', 'mixed_workload_mice_fct_vs_load.png')

    # Queue occupancy graphs
    create_queue_global_peak_graph(all_data, 'queue_global_peak_vs_load.png')
    create_avg_switch_peak_queue_graph(all_data, 'avg_switch_peak_queue_vs_load.png')

    print("\n" + "=" * 60, flush=True)
    print("Graph generation complete!", flush=True)


if __name__ == '__main__':
    main()
