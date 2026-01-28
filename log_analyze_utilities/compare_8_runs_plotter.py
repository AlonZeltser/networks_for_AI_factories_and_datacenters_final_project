"""Utility: compare 8 runs (2 routing methods x 2 scenario types x 2 failure types).

Assumptions
-----------
- Input folder: `log_analyze_utilities/inputs/` contains exactly 8 `.log` files.
- These logs were produced by `ai_factory_network_simulation.py` and include:
  - `Results summary - Parameters:` block
  - `Results summary - Run statistics:` block
  - Job finish lines with per-job step time stats

Outputs
-------
Writes PNGs to `results/` summarizing:
- Step time (avg/p95/p99) comparing flowlet vs adaptive per scenario_type and failure_type (4 plots)
- Job total simulator time comparing flowlet vs adaptive per scenario_type and failure_type (4 plots)
- Tail behavior: CDF of per-step durations (from Job finished line stats we only have aggregate;
  here we parse per-step durations from Step start/finish timestamps for each job) (4 plots)
- Mice latency summary/CDF when sufficient data exists (currently logs provide summary only; we plot bars)
- Port load proxy plots based on end-of-run link utilization and queue lengths present in run statistics

This script has no CLI parameters by design.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INPUT_DIR = os.path.join(ROOT, "log_analyze_utilities", "inputs")
RESULTS_DIR = os.path.join(ROOT, "results")


@dataclass(frozen=True)
class RunKey:
    scenario_type: str  # e.g. "mixed_scenario" or "workload1-dp-heavy"
    failure_type: str  # "no_failures" / "with_failures"
    routing_method: str  # "adaptive" / "flowlet" (ecmp default treated as flowlet)


@dataclass
class RunData:
    path: str
    parameters: Dict[str, object]
    run_stats: Dict[str, object]
    # derived
    scenario_type: str
    failure_type: str
    routing_method: str
    # time series
    step_durations_ms_per_job: Dict[str, List[float]]


_RE_LOADED_CFG = re.compile(r"Loaded configuration from:\s+(?P<path>.+?)\s*$")
_RE_PARAMS_KV = re.compile(r"^(?P<k>[^:]+):\s+(?P<v>.+?)\s*$")
_RE_JOB_FINISHED = re.compile(
    r"\] Job finished\s+job_id=(?P<job_id>\d+)\s+step_time_avg=(?P<avg>[0-9.]+)ms\s+step_time_p95=(?P<p95>[0-9.]+)ms\s+step_time_p99=(?P<p99>[0-9.]+)ms"
)
_RE_JOB_STARTING = re.compile(r"\] Job starting\s+job=(?P<job>\S+)")
_RE_STEP_START = re.compile(r"\] Step starting\s+step=(?P<step>\d+)")
_RE_STEP_FINISH = re.compile(r"\] Step finished\s+step=(?P<step>\d+)")
_RE_SIM_T = re.compile(r"\[sim_t=(?P<t>[0-9.]+)s\]")


def _ensure_dirs() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _list_input_logs() -> List[str]:
    if not os.path.isdir(INPUT_DIR):
        raise FileNotFoundError(f"Input dir not found: {INPUT_DIR}")
    logs = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) if f.endswith(".log")]
    logs.sort()
    if len(logs) != 8:
        raise RuntimeError(
            f"Expected exactly 8 .log files in {INPUT_DIR}, found {len(logs)}: {[os.path.basename(p) for p in logs]}"
        )
    return logs


def _parse_results_block(lines: List[str], start_index: int) -> Tuple[Dict[str, object], int]:
    """Parse a results summary block emitted as k: v lines.

    Returns (dict, next_index_after_block).

    Block termination: next timestamped log line or blank line.
    """
    out: Dict[str, object] = {}
    i = start_index
    while i < len(lines):
        line = lines[i].rstrip("\n")
        # Stop on next log record line like "HH:MM:SS [INFO] ...".
        if re.match(r"^\d{2}:\d{2}:\d{2} \[", line):
            break
        if not line.strip():
            i += 1
            continue
        m = _RE_PARAMS_KV.match(line)
        if m:
            k = m.group("k").strip()
            v_raw = m.group("v").strip()
            # Try parse python literal when applicable (dict/list/bool/num)
            v: object
            try:
                v = ast.literal_eval(v_raw)
            except Exception:
                # Try float/int
                try:
                    if re.fullmatch(r"-?\d+", v_raw):
                        v = int(v_raw)
                    elif re.fullmatch(r"-?\d+\.\d+", v_raw):
                        v = float(v_raw)
                    else:
                        v = v_raw
                except Exception:
                    v = v_raw
            out[k] = v
        i += 1
    return out, i


def _classify_run(params: Dict[str, object], cfg_path: Optional[str]) -> Tuple[str, str, str]:
    scen = str(params.get("scenario", ""))
    if not scen and cfg_path:
        scen = os.path.basename(cfg_path)

    scen_l = scen.lower()

    if "mixed" in scen_l:
        scenario_type = "mixed"
    elif "dp-heavy" in scen_l or "dp_heavy" in scen_l or "dpheavy" in scen_l:
        scenario_type = "dp_heavy"
    else:
        # Fall back to config filename patterns
        base = os.path.basename(cfg_path).lower() if cfg_path else ""
        if "mixed" in base:
            scenario_type = "mixed"
        elif "dp-heavy" in base or "dp_heavy" in base or "dpheavy" in base:
            scenario_type = "dp_heavy"
        else:
            scenario_type = "unknown"

    failure_percent = float(params.get("link_failure_percent", 0.0) or 0.0)
    failure_type = "no_failures" if failure_percent <= 0.0 else "with_failures"

    routing_mode = str(params.get("routing_mode", "")).lower().strip()
    if routing_mode == "adaptive":
        routing_method = "adaptive"
    else:
        # treat ecmp/flowlet/anything else as "flowlet" for the requested comparison
        routing_method = "flowlet"

    return scenario_type, failure_type, routing_method


def _parse_step_durations(lines: List[str]) -> Dict[str, List[float]]:
    """Parse per-step durations by tracking sim_t at Step start/finish per job.

    The log interleaves multiple jobs; a bare "Step starting step=X" belongs to the current job
    context of that logger instance. We infer job name by most recent "Job starting job=...".

    Returns map job_name -> list of durations in ms.
    """
    current_job: Optional[str] = None
    step_start_time: Dict[Tuple[str, int], float] = {}
    out: Dict[str, List[float]] = {}

    for raw in lines:
        line = raw.rstrip("\n")
        m_js = _RE_JOB_STARTING.search(line)
        if m_js:
            current_job = m_js.group("job")
            out.setdefault(current_job, [])
            continue

        if current_job is None:
            continue

        m_t = _RE_SIM_T.search(line)
        if not m_t:
            continue
        t = float(m_t.group("t"))

        m_ss = _RE_STEP_START.search(line)
        if m_ss:
            step = int(m_ss.group("step"))
            step_start_time[(current_job, step)] = t
            continue

        m_sf = _RE_STEP_FINISH.search(line)
        if m_sf:
            step = int(m_sf.group("step"))
            st = step_start_time.get((current_job, step))
            if st is not None and t >= st:
                out.setdefault(current_job, []).append((t - st) * 1000.0)
            continue

    # Compact job names for later matching (tp_heavy / pp_dp / job)
    normalized: Dict[str, List[float]] = {}
    for k, v in out.items():
        if "tp_heavy" in k:
            normalized["tp_heavy"] = v
        elif "pp_dp" in k:
            normalized["pp_dp"] = v
        elif k == "job" or "dp-heavy" in k:
            normalized["job"] = v
        else:
            normalized[k] = v
    return normalized


def parse_log(path: str) -> RunData:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    cfg_path: Optional[str] = None
    for ln in lines[:200]:
        m = _RE_LOADED_CFG.search(ln)
        if m:
            cfg_path = m.group("path").strip()
            break

    params: Dict[str, object] = {}
    run_stats: Dict[str, object] = {}

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if "Results summary - Parameters:" in line:
            params, i = _parse_results_block(lines, i + 1)
            continue
        if "Results summary - Run statistics:" in line:
            run_stats, i = _parse_results_block(lines, i + 1)
            continue
        i += 1

    if not params:
        raise RuntimeError(f"Could not find 'Results summary - Parameters' block in {path}")
    if not run_stats:
        raise RuntimeError(f"Could not find 'Results summary - Run statistics' block in {path}")

    scenario_type, failure_type, routing_method = _classify_run(params, cfg_path)
    step_durations = _parse_step_durations(lines)

    return RunData(
        path=path,
        parameters=params,
        run_stats=run_stats,
        scenario_type=scenario_type,
        failure_type=failure_type,
        routing_method=routing_method,
        step_durations_ms_per_job=step_durations,
    )


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    w = rank - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


def _compute_stats_ms(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"avg": 0.0, "p95": 0.0, "p99": 0.0}
    avg = sum(values) / len(values)
    s = sorted(values)
    return {"avg": avg, "p95": _percentile(s, 95.0), "p99": _percentile(s, 99.0)}


def _get_job_total_time_s(run: RunData, job_key: str) -> float:
    # For single-job scenarios, total run time is good enough.
    # For mixed scenarios, run time corresponds to the global sim end time, so job time differs.
    # We approximate per-job total time using the sum of step durations we parsed.
    step_ms = run.step_durations_ms_per_job.get(job_key, [])
    if step_ms:
        return sum(step_ms) / 1000.0
    return float(run.run_stats.get("total run time (simulator time in seconds)", 0.0) or 0.0)


def _plot_bar_compare(
    *,
    title: str,
    ylabel: str,
    adaptive_vals: List[float],
    flowlet_vals: List[float],
    labels: List[str],
    outfile: str,
) -> None:
    x = list(range(len(labels)))
    width = 0.35

    plt.figure(figsize=(10, 5))
    plt.bar([i - width / 2 for i in x], flowlet_vals, width=width, label="flowlet")
    plt.bar([i + width / 2 for i in x], adaptive_vals, width=width, label="adaptive")
    plt.xticks(x, labels, rotation=0)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.grid(axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=140)
    plt.close()


def _plot_step_stats(run_map: Dict[RunKey, RunData]) -> None:
    for scenario_type in sorted({k.scenario_type for k in run_map}):
        for failure_type in sorted({k.failure_type for k in run_map}):
            # For each job kind present in that scenario type
            if scenario_type == "mixed":
                job_keys = ["tp_heavy", "pp_dp"]
            else:
                job_keys = ["job"]

            for job_key in job_keys:
                rk_a = RunKey(scenario_type, failure_type, "adaptive")
                rk_f = RunKey(scenario_type, failure_type, "flowlet")
                if rk_a not in run_map or rk_f not in run_map:
                    continue

                stats_a = run_map[rk_a].run_stats.get("ai_factory_step_time_ms_per_job", {})
                stats_f = run_map[rk_f].run_stats.get("ai_factory_step_time_ms_per_job", {})

                # stats blocks are dicts like {'tp_heavy': {'step_time_avg_ms': ...}}
                def pull(d: object, key: str) -> Dict[str, float]:
                    if isinstance(d, dict) and key in d and isinstance(d[key], dict):
                        dd = d[key]
                        return {
                            "avg": float(dd.get("step_time_avg_ms", 0.0)),
                            "p95": float(dd.get("step_time_p95_ms", 0.0)),
                            "p99": float(dd.get("step_time_p99_ms", 0.0)),
                        }
                    return {"avg": 0.0, "p95": 0.0, "p99": 0.0}

                s_a = pull(stats_a, job_key)
                s_f = pull(stats_f, job_key)

                labels = ["avg", "p95", "p99"]
                adaptive_vals = [s_a["avg"], s_a["p95"], s_a["p99"]]
                flowlet_vals = [s_f["avg"], s_f["p95"], s_f["p99"]]

                out = os.path.join(
                    RESULTS_DIR,
                    f"compare_step_time_{scenario_type}_{failure_type}_{job_key}.png",
                )
                _plot_bar_compare(
                    title=f"Step time (ms) - {scenario_type} / {failure_type} / {job_key}",
                    ylabel="ms",
                    adaptive_vals=adaptive_vals,
                    flowlet_vals=flowlet_vals,
                    labels=labels,
                    outfile=out,
                )


def _plot_job_time(run_map: Dict[RunKey, RunData]) -> None:
    for scenario_type in sorted({k.scenario_type for k in run_map}):
        for failure_type in sorted({k.failure_type for k in run_map}):
            if scenario_type == "mixed":
                job_keys = ["tp_heavy", "pp_dp"]
            else:
                job_keys = ["job"]

            for job_key in job_keys:
                rk_a = RunKey(scenario_type, failure_type, "adaptive")
                rk_f = RunKey(scenario_type, failure_type, "flowlet")
                if rk_a not in run_map or rk_f not in run_map:
                    continue

                t_a = _get_job_total_time_s(run_map[rk_a], job_key)
                t_f = _get_job_total_time_s(run_map[rk_f], job_key)

                out = os.path.join(
                    RESULTS_DIR,
                    f"compare_job_time_{scenario_type}_{failure_type}_{job_key}.png",
                )
                _plot_bar_compare(
                    title=f"Job time (sim seconds) - {scenario_type} / {failure_type} / {job_key}",
                    ylabel="sim seconds",
                    adaptive_vals=[t_a],
                    flowlet_vals=[t_f],
                    labels=[job_key],
                    outfile=out,
                )


def _plot_cdf(values: List[float], *, title: str, xlabel: str, outfile: str) -> None:
    vals = sorted([v for v in values if v >= 0.0])
    if not vals:
        return
    n = len(vals)
    ys = [i / n for i in range(1, n + 1)]

    plt.figure(figsize=(8, 5))
    plt.plot(vals, ys)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("CDF")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(outfile, dpi=140)
    plt.close()


def _plot_tail_behaviour(run_map: Dict[RunKey, RunData]) -> None:
    for scenario_type in sorted({k.scenario_type for k in run_map}):
        for failure_type in sorted({k.failure_type for k in run_map}):
            for routing_method in ["flowlet", "adaptive"]:
                rk = RunKey(scenario_type, failure_type, routing_method)
                run = run_map.get(rk)
                if run is None:
                    continue

                if scenario_type == "mixed":
                    job_keys = ["tp_heavy", "pp_dp"]
                else:
                    job_keys = ["job"]

                for job_key in job_keys:
                    vals = run.step_durations_ms_per_job.get(job_key, [])
                    out = os.path.join(
                        RESULTS_DIR,
                        f"cdf_step_time_{scenario_type}_{failure_type}_{routing_method}_{job_key}.png",
                    )
                    _plot_cdf(
                        vals,
                        title=f"Step time CDF - {scenario_type}/{failure_type}/{routing_method}/{job_key}",
                        xlabel="step duration (ms)",
                        outfile=out,
                    )


def _plot_mice_summary(run_map: Dict[RunKey, RunData]) -> None:
    # We only have summary in run_stats, not per-flow samples; plot bars of avg/p95/p99.
    for scenario_type in sorted({k.scenario_type for k in run_map}):
        for failure_type in sorted({k.failure_type for k in run_map}):
            rk_a = RunKey(scenario_type, failure_type, "adaptive")
            rk_f = RunKey(scenario_type, failure_type, "flowlet")
            if rk_a not in run_map or rk_f not in run_map:
                continue

            def pull(run: RunData) -> Dict[str, float]:
                return {
                    "avg": float(run.run_stats.get("mice_fct_avg_ms", 0.0) or 0.0),
                    "p95": float(run.run_stats.get("mice_fct_p95_ms", 0.0) or 0.0),
                    "p99": float(run.run_stats.get("mice_fct_p99_ms", 0.0) or 0.0),
                }

            a = pull(run_map[rk_a])
            f = pull(run_map[rk_f])

            labels = ["avg", "p95", "p99"]
            out = os.path.join(RESULTS_DIR, f"compare_mice_{scenario_type}_{failure_type}.png")
            _plot_bar_compare(
                title=f"Mice FCT (ms) - {scenario_type} / {failure_type}",
                ylabel="ms",
                adaptive_vals=[a[x] for x in labels],
                flowlet_vals=[f[x] for x in labels],
                labels=labels,
                outfile=out,
            )


def _plot_port_load_proxy(run_map: Dict[RunKey, RunData]) -> None:
    # The logs currently include only end-of-run aggregates.
    # We'll plot a simple comparison of link utilization and queue proxies.
    for scenario_type in sorted({k.scenario_type for k in run_map}):
        for failure_type in sorted({k.failure_type for k in run_map}):
            rk_a = RunKey(scenario_type, failure_type, "adaptive")
            rk_f = RunKey(scenario_type, failure_type, "flowlet")
            if rk_a not in run_map or rk_f not in run_map:
                continue

            def pull(run: RunData) -> Dict[str, float]:
                return {
                    "link_avg_util_%": float(run.run_stats.get("link average utilization percentage", 0.0) or 0.0),
                    "global_max_port_peak_q_pkts": float(run.run_stats.get("global_max_port_peak_queue_len (packets)", 0.0) or 0.0),
                    "avg_node_peak_egress_q_pkts": float(run.run_stats.get("avg_node_peak_egress_queue_len (packets)", 0.0) or 0.0),
                }

            a = pull(run_map[rk_a])
            f = pull(run_map[rk_f])

            labels = list(a.keys())
            out = os.path.join(RESULTS_DIR, f"compare_port_load_{scenario_type}_{failure_type}.png")
            _plot_bar_compare(
                title=f"Port/link load proxies - {scenario_type} / {failure_type}",
                ylabel="(various units)",
                adaptive_vals=[a[k] for k in labels],
                flowlet_vals=[f[k] for k in labels],
                labels=labels,
                outfile=out,
            )


def main() -> None:
    _ensure_dirs()
    logs = _list_input_logs()

    runs = [parse_log(p) for p in logs]

    run_map: Dict[RunKey, RunData] = {}
    for r in runs:
        key = RunKey(r.scenario_type, r.failure_type, r.routing_method)
        if key in run_map:
            raise RuntimeError(
                f"Duplicate key {key} from {os.path.basename(run_map[key].path)} and {os.path.basename(r.path)}"
            )
        run_map[key] = r

    # Basic sanity: must contain 2 x 2 x 2 combos
    needed = {
        RunKey(st, ft, rm)
        for st in ("mixed", "dp_heavy")
        for ft in ("no_failures", "with_failures")
        for rm in ("flowlet", "adaptive")
    }

    missing = sorted(list(needed - set(run_map.keys())), key=lambda x: (x.scenario_type, x.failure_type, x.routing_method))
    if missing:
        raise RuntimeError(
            "Missing expected runs (did you put the right 8 logs in inputs?):\n"
            + "\n".join(str(m) for m in missing)
        )

    _plot_step_stats(run_map)
    _plot_job_time(run_map)
    _plot_tail_behaviour(run_map)
    _plot_mice_summary(run_map)
    _plot_port_load_proxy(run_map)

    print(f"Wrote plots to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
