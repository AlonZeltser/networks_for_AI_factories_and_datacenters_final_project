import datetime
import logging
import os
from typing import Any, Dict, List, Optional, Tuple


def visualize_send_timeline(
    packet_timeline: List[Tuple[float, int]],
    total_time: float,
    routing_mode: str = "",
    out_dir: str = "results",
    num_bins: int = 200,
) -> Optional[str]:
    """Create a histogram showing the distribution of sends over the simulation timeline.

    This visualization shows how messaging activity is distributed across time,
    highlighting bursts and uneven distribution patterns.

    Args:
        packet_timeline: list of (birth_time, size_bytes) tuples for each packet
        total_time: total simulation time in seconds
        routing_mode: routing mode string for the title (e.g., 'ecmp', 'adaptive')
        out_dir: output directory for the PNG file
        num_bins: number of time bins for the histogram

    Returns:
        Path to saved file, or None if visualization failed.
    """
    if not packet_timeline:
        logging.warning("No packet timeline data to visualize")
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logging.warning("matplotlib not available, skipping timeline visualization")
        return None

    try:
        # Extract times and sizes
        times = np.array([t for t, _ in packet_timeline])
        sizes = np.array([s for _, s in packet_timeline])

        # Create time bins
        if total_time <= 0:
            total_time = max(times) if len(times) > 0 else 1.0
        bin_edges = np.linspace(0, total_time, num_bins + 1)

        # Calculate bytes sent per bin
        bytes_per_bin = np.zeros(num_bins)
        packets_per_bin = np.zeros(num_bins)
        for t, s in packet_timeline:
            bin_idx = min(int(t / total_time * num_bins), num_bins - 1)
            bytes_per_bin[bin_idx] += s
            packets_per_bin[bin_idx] += 1

        # Convert to MB for readability
        mb_per_bin = bytes_per_bin / (1024 * 1024)

        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Time axis in microseconds for better readability
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2 * 1e6  # convert to µs
        bin_width = (bin_edges[1] - bin_edges[0]) * 1e6

        # Top plot: Data volume (MB)
        colors1 = plt.cm.Blues(np.linspace(0.4, 0.9, num_bins))
        ax1.bar(bin_centers, mb_per_bin, width=bin_width * 0.9, color=colors1, edgecolor='navy', linewidth=0.5)
        ax1.set_ylabel('Data Sent (MB)', fontsize=11)
        ax1.set_title(f'Messaging Distribution Over Time{" (" + routing_mode.upper() + ")" if routing_mode else ""}',
                      fontsize=14, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)

        # Add average line
        avg_mb = np.mean(mb_per_bin)
        ax1.axhline(y=avg_mb, color='red', linestyle='--', linewidth=1.5, label=f'Avg: {avg_mb:.3f} MB')
        ax1.legend(loc='upper right')

        # Bottom plot: Packet count
        colors2 = plt.cm.Greens(np.linspace(0.4, 0.9, num_bins))
        ax2.bar(bin_centers, packets_per_bin, width=bin_width * 0.9, color=colors2, edgecolor='darkgreen', linewidth=0.5)
        ax2.set_xlabel('Time (µs)', fontsize=11)
        ax2.set_ylabel('Packets Sent', fontsize=11)
        ax2.grid(axis='y', alpha=0.3)

        # Add average line
        avg_packets = np.mean(packets_per_bin)
        ax2.axhline(y=avg_packets, color='red', linestyle='--', linewidth=1.5, label=f'Avg: {avg_packets:.1f} packets')
        ax2.legend(loc='upper right')

        # Add statistics text
        total_mb = sum(mb_per_bin)
        total_packets = len(packet_timeline)
        max_mb = max(mb_per_bin)
        min_mb = min(mb_per_bin[mb_per_bin > 0]) if any(mb_per_bin > 0) else 0
        stats_text = (f"Total: {total_mb:.2f} MB | {total_packets:,} packets | "
                      f"Duration: {total_time*1e6:.2f} µs | Peak: {max_mb:.3f} MB/bin")
        fig.text(0.5, 0.02, stats_text, ha='center', fontsize=10, style='italic')

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.1)

        # Save figure
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"send_timeline_{routing_mode}_{timestamp}.png" if routing_mode else f"send_timeline_{timestamp}.png"
        filepath = os.path.join(out_dir, filename)
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        logging.info(f"Send timeline graph saved to: {filepath}")
        return filepath

    except Exception as e:
        logging.exception(f"Failed to create send timeline visualization: {e}")
        return None


def visualize_experiment_results(results: List[Dict[str, Dict[str, Any]]],
                                 out_dir: str = "results") -> None:
    """Visualize experiment results including send timeline distribution.

    Args:
        results: list of run-result dicts.
        out_dir: output directory for visualization files.
    """
    for result in results:
        packet_timeline = result.get('packet_timeline', [])
        params = result.get('parameters summary', {})
        stats = result.get('run statistics', {})
        routing_mode = params.get('routing_mode', '')
        total_time = stats.get('total run time (simulator time in seconds)', 0)

        if packet_timeline:
            visualize_send_timeline(packet_timeline, total_time, routing_mode, out_dir)


__all__ = ["visualize_experiment_results", "visualize_send_timeline"]
