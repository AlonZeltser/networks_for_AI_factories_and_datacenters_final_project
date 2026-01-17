import math
import os
from types import SimpleNamespace
from typing import Dict, Any, List, Tuple, Optional

import matplotlib as mpl

from visualization.visualizer import plot_hosts_received_histogram


def _sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))


def _get_parameters(run: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    # Always return a dict to keep callers safe
    return run.get('parameters summary') or {}


def _get_run_stats(run: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    # Always return a dict to keep callers safe
    return run.get('run statistics') or {}


def _to_float(v: Optional[object], default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        # cast to str first to accept arbitrary objects that implement __str__
        return float(str(v))
    except Exception:
        return default


# --- Data collection and aggregation helpers ---

def _collect_group_entries(results: List[Dict[str, Dict[str, Any]]]) -> Dict[
    Optional[str], List[Tuple[float, float, float, float, float, float, float]]]:
    """Parse raw results list into a dict keyed by k with tuples per run:
    (failure_rate, avg_delivery_time, avg_utilization, delivered_straight_pct, dropped_pct,
     avg_path_length, max_path_length)
    """
    groups: Dict[Optional[str], List[Tuple[float, float, float, float, float, float, float]]] = {}
    for run in results:
        params = _get_parameters(run)
        stats = _get_run_stats(run)
        # extract k (may be missing)
        k = params.get('k') if isinstance(params, dict) else None

        # extract failure rate (support both keys and strings like "5%")
        rate_raw = None
        if isinstance(params, dict):
            rate_raw = params.get('link_failure_percent')
            if rate_raw is None:
                rate_raw = params.get('link failure percent')

        # normalize percent strings and skip missing/invalid rates
        if isinstance(rate_raw, str) and rate_raw.strip().endswith('%'):
            rate_str = rate_raw.strip().rstrip('%').strip()
        else:
            rate_str = rate_raw

        if rate_str is None or (isinstance(rate_str, str) and rate_str.strip() == ""):
            # skip runs without a usable failure-rate
            continue

        try:
            rate_val = float(str(rate_str))
        except Exception:
            # skip runs where rate cannot be parsed as a float
            continue

        # extract average delivery time and average utilization using expected keys
        avg_delivery = stats.get('links average delivery time') if isinstance(stats, dict) else None
        if avg_delivery is None:
            avg_delivery = stats.get('links_average_delivery_time') if isinstance(stats, dict) else None
        avg_delivery_val = _to_float(avg_delivery)

        avg_util = stats.get('link average utilization') if isinstance(stats, dict) else None
        if avg_util is None:
            avg_util = stats.get('link_average_utilization') if isinstance(stats, dict) else None
        avg_util_val = _to_float(avg_util)

        # extract packet delivery/drop percentages
        delivered_straight_pct = None
        dropped_pct = None
        if isinstance(stats, dict):
            delivered_straight_pct = stats.get('delivered straight messages percentage')
            if delivered_straight_pct is None:
                delivered_straight_pct = stats.get('delivered_straight_messages_percentage') or stats.get(
                    'delivered straight messages %')

            dropped_pct = stats.get('dropped messages percentage')
            if dropped_pct is None:
                dropped_pct = stats.get('dropped messages %') or stats.get('dropped_messages_percentage')

        delivered_straight_pct_val = _to_float(delivered_straight_pct)
        dropped_pct_val = _to_float(dropped_pct)

        # extract path lengths (avg and max). Support different possible keys used in stats
        avg_path = None
        max_path = None
        if isinstance(stats, dict):
            avg_path = stats.get('avg path length') or stats.get('avg_path_length') or stats.get('average path length')
            max_path = stats.get('max path length') or stats.get('max_path_length')

        avg_path_val = _to_float(avg_path)
        max_path_val = _to_float(max_path)

        groups.setdefault(k, []).append(
            (rate_val, avg_delivery_val, avg_util_val, delivered_straight_pct_val,
             dropped_pct_val, avg_path_val, max_path_val))
    return groups


def _aggregate_by_rate(entries: List[Tuple[float, float, float, float, float, float, float]]) -> Tuple[
    List[float], List[float], List[float], List[float], List[float], List[float], List[float]]:
    """Aggregate possibly multiple runs per failure-rate into averaged series per metric.
    Returns: rates, avg_deliveries, avg_utils, avg_delivered_straight_pcts, avg_dropped_pcts, avg_paths, max_paths
    """
    by_rate: Dict[float, List[Tuple[float, float, float, float, float, float]]] = {}
    for rate_val, delivery_val, util_val, ds_pct, d_pct, avg_path_val, max_path_val in entries:
        by_rate.setdefault(rate_val, []).append(
            (delivery_val, util_val, ds_pct, d_pct, avg_path_val, max_path_val))

    rates_sorted = sorted(by_rate.keys())
    rates: List[float] = []
    avg_deliveries: List[float] = []
    avg_utils: List[float] = []
    avg_delivered_straight_pcts: List[float] = []
    avg_dropped_pcts: List[float] = []
    avg_paths: List[float] = []
    max_paths: List[float] = []

    for r in rates_sorted:
        vals = by_rate[r]
        if not vals:
            continue
        deliveries = [v[0] for v in vals]
        utils = [v[1] for v in vals]
        ds_pcts = [v[2] for v in vals]
        d_pcts = [v[3] for v in vals]
        avg_path_vals = [v[4] for v in vals]
        max_path_vals = [v[5] for v in vals]
        rates.append(r)
        avg = lambda arr: float(sum(arr)) / float(len(arr)) if arr else 0.0
        avg_deliveries.append(avg(deliveries))
        avg_utils.append(avg(utils))
        avg_delivered_straight_pcts.append(avg(ds_pcts))
        avg_dropped_pcts.append(avg(d_pcts))
        avg_paths.append(avg(avg_path_vals))
        max_paths.append(max(max_path_vals) if max_path_vals else 0.0)

    return rates, avg_deliveries, avg_utils, avg_delivered_straight_pcts, avg_dropped_pcts, avg_paths, max_paths


# --- Plot helpers ---

def _plot_time_and_utilization(plt, k_val: Optional[str], rates: List[float], avg_deliveries: List[float],
                               avg_utils: List[float], out_dir: str) -> Optional[str]:
    if not rates:
        return None
    fig, ax1 = plt.subplots()
    color_time = 'tab:blue'
    ax1.set_xlabel('link failure percent')
    ax1.set_ylabel('avg link delivery time (s)', color=color_time)
    ax1.plot(rates, avg_deliveries, marker='o', color=color_time, label='avg link delivery time')
    ax1.tick_params(axis='y', labelcolor=color_time)

    ax2 = ax1.twinx()
    color_util = 'tab:red'
    ax2.set_ylabel('avg link utilization (%)', color=color_util)
    # convert fraction to percentage for plotting
    ax2.plot(rates, [100.0 * float(x) for x in avg_utils], marker='s', color=color_util,
             label='avg link utilization (%)')
    ax2.tick_params(axis='y', labelcolor=color_util)

    title_k = f"k={k_val}" if k_val is not None else "k=unknown"
    ax1.set_title(f"Average link delivery time and utilization vs failure rate ({title_k})")
    fig.tight_layout()

    safe_k = _sanitize_filename(str(k_val))
    # filename requested: start with 'exp' and include k info + links_load suffix
    out_path = os.path.join(out_dir, f"exp_k_{safe_k}_links_load.png")
    try:
        fig.savefig(out_path)
    finally:
        plt.close(fig)
    return out_path


def _plot_delivery_stats(plt, k_val: Optional[str], rates: List[float], ds_pcts: List[float],
                         d_pcts: List[float], out_dir: str) -> Optional[str]:
    if not rates:
        return None
    fig2, ax = plt.subplots()
    ax.set_xlabel('link failure percent')
    ax.set_ylabel('messages (%)')
    ax.plot(rates, ds_pcts, marker='o', color='tab:green', label='delivered (straight) %')
    ax.plot(rates, d_pcts, marker='s', color='tab:purple', label='dropped %')
    title_k = f"k={k_val}" if k_val is not None else "k=unknown"
    ax.set_title(f"Message delivery outcomes vs failure rate ({title_k})")
    ax.legend()
    fig2.tight_layout()

    safe_k = _sanitize_filename(str(k_val))
    out_path2 = os.path.join(out_dir, f"experiment_k_{safe_k}_delivery_stats.png")
    try:
        fig2.savefig(out_path2)
    finally:
        plt.close(fig2)
    return out_path2


def _plot_path_lengths(plt, k_val: Optional[str], rates: List[float], avg_paths: List[float], max_paths: List[float],
                       out_dir: str) -> Optional[str]:
    """Plot average and max path length vs failure rate."""
    if not rates:
        return None
    fig, ax = plt.subplots()
    ax.set_xlabel('link failure percent')
    ax.set_ylabel('path length (hops)')
    ax.plot(rates, avg_paths, marker='o', color='tab:blue', label='avg path length')
    ax.plot(rates, max_paths, marker='s', color='tab:red', label='max path length')
    title_k = f"k={k_val}" if k_val is not None else "k=unknown"
    ax.set_title(f"Path length (avg/max) vs failure rate ({title_k})")
    ax.legend()
    fig.tight_layout()

    safe_k = _sanitize_filename(str(k_val))
    out_path = os.path.join(out_dir, f"experiment_k_{safe_k}_path_lengths.png")
    try:
        fig.savefig(out_path)
    finally:
        plt.close(fig)
    return out_path


def _plot_loss_and_path_vs_k(plt, rate_val: float, ks: List[float], dropped_pcts: List[float], avg_paths: List[float],
                             out_dir: str) -> Optional[str]:
    """For a single failure rate, plot dropped % and avg path length vs k."""
    if not ks:
        return None
    fig, ax1 = plt.subplots()
    ax1.set_xlabel('k')
    ax1.set_ylabel('dropped messages (%)', color='tab:purple')
    ax1.plot(ks, dropped_pcts, marker='o', color='tab:purple', label='dropped %')
    ax1.tick_params(axis='y', labelcolor='tab:purple')

    ax2 = ax1.twinx()
    ax2.set_ylabel('avg path length (hops)', color='tab:blue')
    ax2.plot(ks, avg_paths, marker='s', color='tab:blue', label='avg path length')
    ax2.tick_params(axis='y', labelcolor='tab:blue')

    title = f"Packet loss and avg path length vs k (failure={rate_val}%)"
    ax1.set_title(title)
    fig.tight_layout()

    safe_rate = _sanitize_filename(str(rate_val))
    out_path = os.path.join(out_dir, f"exp_failure_{safe_rate}_k_stats.png")
    try:
        fig.savefig(out_path)
    finally:
        plt.close(fig)
    return out_path


def visualize_experiment_results(results: List[Dict[str, Dict[str, Any]]],
                                 out_dir: str = "results/experiments") -> None:
    """
    Create one plot per distinct k value found in the provided `results` list.

    - results: list of run-result dicts (each should contain 'parameters summary' and 'run statistics')
    - out_dir: base directory where plots will be saved
    - visualize: single boolean parameter that controls whether plots are opened (displayed) after save.

    The plot for each k has:
      - x axis: link-failure rate (from parameters summary: 'link_failure_percent' or 'link failure percent')
      - left y axis: average link transmission time ('links average delivery time')
      - right y axis: average link utilization ('link average utilization')


    """

    mpl.use('Agg')

    # import pyplot after backend selection
    try:
        import matplotlib.pyplot as plt
    except Exception:
        # fallback: create a dummy namespace to avoid NameError in non-plotting environments
        plt = SimpleNamespace(show=lambda *a, **k: None, pause=lambda *a, **k: None, close=lambda *a, **k: None,
                              subplots=lambda *a, **k: (None, SimpleNamespace(plot=lambda *a, **k: None,
                                                                              set_xlabel=lambda *a, **k: None,
                                                                              set_ylabel=lambda *a, **k: None,
                                                                              tick_params=lambda *a, **k: None,
                                                                              set_title=lambda *a, **k: None)))

    # Collect and organize
    groups = _collect_group_entries(results)

    # ensure output dir exists
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass

    # For each k, aggregate and plot via dedicated helpers
    for k_val, entries in groups.items():
        if not entries:
            continue

        rates, avg_deliveries, avg_utils, ds_pcts, d_pcts, avg_paths, max_paths = _aggregate_by_rate(entries)

        # Skip if all metrics are effectively zero
        if (all(math.isclose(x, 0.0, abs_tol=1e-12) for x in avg_deliveries)
                and all(math.isclose(x, 0.0, abs_tol=1e-12) for x in avg_utils)
                and all(math.isclose(x, 0.0, abs_tol=1e-12) for x in ds_pcts)
                and all(math.isclose(x, 0.0, abs_tol=1e-12) for x in d_pcts)
                and all(math.isclose(x, 0.0, abs_tol=1e-12) for x in avg_paths)):
            continue

        # Three dedicated plot routines
        _plot_time_and_utilization(plt, k_val, rates, avg_deliveries, avg_utils, out_dir)
        _plot_delivery_stats(plt, k_val, rates, ds_pcts, d_pcts, out_dir)
        _plot_path_lengths(plt, k_val, rates, avg_paths, max_paths, out_dir)

    # --- New: for each failure rate create a plot with x axis = k and y = dropped % and avg path length
    failure_groups: Dict[float, List[Tuple[Optional[object], float, float]]] = {}
    for k_val, entries in groups.items():
        for (rate_val, _delivery, _util, _ds, d_pct, avg_path, _max_path) in entries:
            try:
                rate_key = float(rate_val)
            except Exception:
                # skip invalid rate
                continue
            # Normalize k: only include numeric k values for the k-vs plots (skip unknown/non-numeric)
            if k_val is None:
                continue
            try:
                k_numeric = int(float(str(k_val)))
            except Exception:
                # skip non-numeric k values (e.g., 'unknown') for these plots
                continue
            failure_groups.setdefault(rate_key, []).append((k_numeric, _to_float(d_pct), _to_float(avg_path)))

    # For each failure rate, aggregate per-k and plot
    for rate_val, items in failure_groups.items():
        # aggregate by k (average if multiple entries per k)
        by_k: Dict[object, List[Tuple[float, float]]] = {}
        for k_raw, d_pct, avg_path in items:
            # normalize k to numeric if possible
            if k_raw is None:
                k_key = 'unknown'
            else:
                try:
                    k_key = int(float(str(k_raw)))
                except Exception:
                    k_key = str(k_raw)
            by_k.setdefault(k_key, []).append((d_pct, avg_path))

        # sort keys: numeric ks first (by numeric value), then non-numeric keys lexicographically
        def _k_sort_key(x: object):
            # return tuple (is_non_numeric, numeric_value_or_0, str_representation)
            if isinstance(x, (int, float)):
                return (0, float(x), str(x))
            if isinstance(x, str):
                s = x.strip()
                # treat 'unknown' as non-numeric explicitly
                if s.lower() == 'unknown':
                    return (1, 0.0, s)
                # numeric-like string?
                if s.replace('.', '', 1).lstrip('-').isdigit():
                    try:
                        return (0, float(s), s)
                    except Exception:
                        return (1, 0.0, s)
                return (1, 0.0, s)
            # fallback: try to parse as float from string
            try:
                f = float(str(x))
                return (0, f, str(x))
            except Exception:
                return (1, 0.0, str(x))

        ks_sorted = sorted(by_k.keys(), key=_k_sort_key)
        ks: List[float] = []
        dropped_avgs: List[float] = []
        avg_path_avgs: List[float] = []
        for k in ks_sorted:
            # convert key to numeric; skip non-numeric keys (like 'unknown') because x-axis must be numeric
            try:
                k_num = float(k) if isinstance(k, (int, float)) else float(str(k))
            except Exception:
                # skip non-numeric k
                continue
            vals = by_k[k]
            drops = [v[0] for v in vals]
            paths = [v[1] for v in vals]
            ks.append(k_num)
            dropped_avgs.append(float(sum(drops)) / float(len(drops)) if drops else 0.0)
            avg_path_avgs.append(float(sum(paths)) / float(len(paths)) if paths else 0.0)

        # only plot if we have data
        if ks:
            _plot_loss_and_path_vs_k(plt, rate_val, ks, dropped_avgs, avg_path_avgs, out_dir)

    # Per-run histograms: for each original run in the provided results list, if hosts received counts exist,
    # save a histogram. We build a simple run name from available parameters (k and link failure percent).
    for run in results:
        params = _get_parameters(run)
        stats = _get_run_stats(run)
        hosts_received = stats.get('hosts received counts') if isinstance(stats, dict) else None
        # accept either dict mapping host->count OR a sequence/list of counts
        if hosts_received and isinstance(hosts_received, (dict, list, tuple)):
            # construct short run name
            k = params.get('k') if isinstance(params, dict) else None
            lf = params.get('link_failure_percent') if isinstance(params, dict) else None
            if lf is None:
                lf = params.get('link failure percent') if isinstance(params, dict) else None
            run_name = f"k={k}_lf={lf}" if k is not None or lf is not None else "run"
            try:
                plot_hosts_received_histogram(hosts_received, run_name, out_dir=out_dir)
            except Exception:
                # do not let histogram saving break the overall visualization process
                pass


__all__ = ['visualize_experiment_results']
