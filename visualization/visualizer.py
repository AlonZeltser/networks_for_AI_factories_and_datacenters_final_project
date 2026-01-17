import datetime
import logging
import os
from typing import Optional, Dict, Any, Sequence, Union


def visualize_topology(topop_name: str, entities: Dict[Any, Any], spacing: float = 2.0, show: bool = True) -> Optional[
    str]:
    """Create a visualization of the topology using networkx + matplotlib if available.

    If `show` is True the function will attempt to display the figure; if False the figure
    will only be saved to disk (no GUI). The function returns the path to the saved file if saved, otherwise None.
    """
    # Lazy import so visualization is optional. Reduce logging noise from third-party libs.
    _logging = None
    _prev_levels = {}
    noisy_loggers = ['matplotlib', 'PIL', 'pillow', 'networkx', 'pyparsing', 'pydot', 'pydotplus', 'graphviz']
    try:
        import logging as _logging
        for lname in noisy_loggers:
            try:
                _prev_levels[lname] = _logging.getLogger(lname).level
                _logging.getLogger(lname).setLevel(_logging.WARNING)
            except Exception:
                _prev_levels[lname] = None
        # Use a non-interactive backend so saving works in headless environments.
        import matplotlib as mpl
        mpl.use('Agg')
        import matplotlib.pyplot as plt
        import networkx as nx
    except Exception:
        # restore logging levels if we changed them
        try:
            if _logging is not None:
                for lname, prev in _prev_levels.items():
                    try:
                        if prev is not None:
                            _logging.getLogger(lname).setLevel(prev)
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    # Build graph
    # Use a MultiGraph so multiple physical links between the same 2 nodes are preserved.
    G = nx.MultiGraph()
    node_types = {}
    # Add node vertices for non-link entities
    for name, ent in entities.items():
        if ent is None:
            continue
        cls_name = ent.__class__.__name__.lower()
        if cls_name.startswith("host"):
            node_types[name] = "host"
            G.add_node(name)
        elif cls_name.startswith("switch"):
            node_types[name] = "switch"
            G.add_node(name)

    def _link_endpoints(link_obj):
        """Return (node_name1, node_name2) for a link object.

        Supports both the newer ports-based Link model (link.port1/port2.owner) and the older
        direct node reference model (link.node1/node2).
        """
        # Newer model: link.port1/port2 are Ports whose `.owner` is a NetworkNode
        try:
            p1 = getattr(link_obj, "port1", None)
            p2 = getattr(link_obj, "port2", None)
            o1 = getattr(p1, "owner", None)
            o2 = getattr(p2, "owner", None)
            n1 = getattr(o1, "name", None)
            n2 = getattr(o2, "name", None)
            if n1 and n2:
                return n1, n2
        except Exception:
            pass

        # Older model (for backwards compatibility)
        try:
            n1 = getattr(getattr(link_obj, "node1", None), "name", None)
            n2 = getattr(getattr(link_obj, "node2", None), "name", None)
            if n1 and n2:
                return n1, n2
        except Exception:
            pass

        return None, None

    # Add edges from Link objects
    for name, ent in entities.items():
        if ent is None:
            continue

        # Heuristic: treat any entity that looks like a link as a potential edge
        if hasattr(ent, "port1") and hasattr(ent, "port2"):
            n1, n2 = _link_endpoints(ent)
            if n1 and n2:
                # Use link name as the multi-edge key so each physical link is distinct.
                G.add_edge(n1, n2, key=name, label=name, _link_name=name)
        elif hasattr(ent, "node1") and hasattr(ent, "node2"):
            # legacy link shape
            n1, n2 = _link_endpoints(ent)
            if n1 and n2:
                G.add_edge(n1, n2, key=name, label=name, _link_name=name)

    if G.number_of_nodes() == 0:
        print("No nodes to visualize in the topology.")
        return None

    # Prefer a layered tree-like layout (core -> aggregation -> edge -> hosts) when node naming follows
    # the fat-tree conventions. Otherwise fall back to graphviz or spring layout.
    layers = []  # initialize so it's available for sizing even if classification fails
    try:
        # classify nodes by name prefixes commonly used in fat-tree network
        cores = sorted([n for n in G.nodes() if str(n).startswith('core_switch')])
        aggs = sorted([n for n in G.nodes() if str(n).startswith('agg_switch')])
        edges = sorted([n for n in G.nodes() if str(n).startswith('edge_switch')])
        hosts = sorted([n for n in G.nodes() if str(n).startswith('host')])

        # Also support the AI-Factory SU naming scheme:
        #   spines: su<id>_spine<k>
        #   leaves: su<id>_leaf<k>
        #   servers: su<id>_leaf<k>_srv<k>
        su_spines = sorted([n for n in G.nodes() if '_spine' in str(n) and str(n).startswith('su')])
        su_leaves = sorted([n for n in G.nodes() if '_leaf' in str(n) and str(n).startswith('su') and '_srv' not in str(n)])
        su_hosts = sorted([n for n in G.nodes() if '_srv' in str(n) and str(n).startswith('su')])

        # If this looks like an SU topology, prefer its 3-layer layout.
        if su_spines and su_leaves and su_hosts:
            layers = [su_spines, su_leaves, su_hosts]
        else:
            layers = [cores, aggs, edges, hosts]
            # keep only non-empty layers, but preserve order
            layers = [layer for layer in layers if layer]

        if len(layers) >= 2:
            pos = {}
            top = 1.0
            bottom = 0.0
            step = (top - bottom) / (len(layers) - 1) if len(layers) > 1 else 0

            for i, layer in enumerate(layers):
                y = top - i * step
                m = len(layer)
                if m == 1:
                    xs = [0.5]
                else:
                    # spread nodes horizontally with a center and a step that depends on spacing
                    center = (m - 1) / 2.0
                    step_x = spacing / max(1, (m - 1))
                    xs = [0.5 + (j - center) * step_x for j in range(m)]
                for node, x in zip(layer, xs):
                    pos[node] = (x, y)

            # Place any leftover nodes (not matched by prefixes) in the middle row(s)
            leftover = [n for n in G.nodes() if n not in pos]
            if leftover:
                mid_y = (top + bottom) / 2
                m = len(leftover)
                if m == 1:
                    xs = [0.5]
                else:
                    center = (m - 1) / 2.0
                    step_x = spacing / max(1, (m - 1))
                    xs = [0.5 + (j - center) * step_x for j in range(m)]
                for node, x in zip(leftover, xs):
                    pos[node] = (x, mid_y)
        else:
            # Fallback to graphviz or spring layout
            try:
                pos = nx.nx_pydot.graphviz_layout(G, prog="dot")
            except Exception:
                pos = nx.spring_layout(G, seed=42)
    except Exception:
        # In case anything unexpected happens, fallback to spring layout
        try:
            pos = nx.nx_pydot.graphviz_layout(G, prog="dot")
        except Exception:
            pos = nx.spring_layout(G, seed=42)

    # Ensure layers has a usable default for sizing if classification failed
    if not layers:
        layers = [list(G.nodes())]

    # Node styling
    colors = []
    sizes = []
    for n in G.nodes():
        t = node_types.get(n, "switch")
        if t == "host":
            colors.append("lightblue")
            # make hosts slightly larger and scale with spacing so labels are more visible
            sizes.append(int(300 * max(1.0, spacing)))
        else:
            colors.append("orange")
            sizes.append(int(900 * max(1.0, spacing)))

    # compute figure size: allow override, otherwise scale with widest layer and number of layers
    widest = max((len(layer) for layer in layers), default=1)
    fig_w = max(12, int(3 + widest * 1.5 * spacing))
    fig_h = max(8, int(2 + len(layers) * 2.0))

    fig = plt.figure(figsize=(fig_w, fig_h))
    # increase font sizes so labels are readable
    base_font = max(8, int(8 * max(1.0, spacing)))
    # Build labels that include host IPs where available (host name on first line, IP on second)
    labels = {}
    # Also print a concise mapping of host -> IP to the console for easy reference
    host_ip_list = []
    for n in G.nodes():
        if node_types.get(n) == 'host':
            ent = entities.get(n)
            ip = None
            try:
                ip = getattr(ent, 'ip_address', None)
            except Exception:
                ip = None
            ip_str = str(ip) if ip is not None else ''
            # two-line label: 'name\nip' to place IP clearly under the host name
            labels[n] = f"{n}\n{ip_str}" if ip_str else n
            host_ip_list.append((n, ip_str))
        else:
            labels[n] = n

    """
    if host_ip_list:
        print("Hosts and IP addresses:")
        for hn, hip in host_ip_list:
            print(f"  {hn}: {hip if hip else '<no IP>'}")
    """

    # draw nodes and edges first (without labels), then draw our custom labels so IPs appear
    nx.draw(G, pos, with_labels=False, node_color=colors, node_size=sizes)
    # Explicitly annotate host nodes using matplotlib.text so IPs show reliably
    ax = plt.gca()

    # --- Edges (aggregated) ---
    # MultiGraph can contain many parallel physical links. For readability we aggregate
    # them into a single straight edge per node-pair and annotate with multiplicity.
    from collections import defaultdict

    pair_to_keys = defaultdict(list)  # (min(u,v), max(u,v)) -> [edge_key,...]
    for u, v, key in G.edges(keys=True):
        pair = tuple(sorted((u, v)))
        pair_to_keys[pair].append(key)

    # determine per-pair style: failed if any underlying link is failed
    healthy_pairs = []  # list of (u, v, count)
    failed_pairs = []   # list of (u, v, count)

    for (u, v), keys in pair_to_keys.items():
        any_failed = False
        for key in keys:
            data = G.get_edge_data(u, v, key) or {}
            link_name = data.get('label') or data.get('_link_name') or key
            link_obj = entities.get(link_name)
            if link_obj is not None and getattr(link_obj, 'failed', False):
                any_failed = True
                break
        if any_failed:
            failed_pairs.append((u, v, len(keys)))
        else:
            healthy_pairs.append((u, v, len(keys)))

    # draw healthy (thin) then failed (thick) edges
    for (u, v, count) in healthy_pairs:
        coll = nx.draw_networkx_edges(
            G,
            pos,
            edgelist=[(u, v)],
            edge_color='gray',
            style='solid',
            width=1.8,
            alpha=0.9,
            ax=ax,
        )
        try:
            coll.set_zorder(1)
        except Exception:
            pass

    for (u, v, count) in failed_pairs:
        coll = nx.draw_networkx_edges(
            G,
            pos,
            edgelist=[(u, v)],
            edge_color='red',
            style='dashed',
            width=6.0,
            alpha=0.95,
            ax=ax,
        )
        try:
            coll.set_zorder(5)
        except Exception:
            pass

    # draw multiplicity labels at edge midpoints
    for (u, v), keys in pair_to_keys.items():
        if not keys:
            continue
        count = len(keys)
        if count <= 1:
            continue  # no need to clutter with x1

        x1, y1 = pos[u]
        x2, y2 = pos[v]
        lx, ly = (x1 + x2) / 2.0, (y1 + y2) / 2.0

        any_failed = False
        for key in keys:
            data = G.get_edge_data(u, v, key) or {}
            link_name = data.get('label') or data.get('_link_name') or key
            link_obj = entities.get(link_name)
            if link_obj is not None and getattr(link_obj, 'failed', False):
                any_failed = True
                break

        lab_color = 'red' if any_failed else 'black'
        lab_text = f"x{count}" + (" (FAILED)" if any_failed else "")
        try:
            ax.text(
                lx,
                ly,
                lab_text,
                fontsize=max(7, int(base_font * 0.85)),
                color=lab_color,
                fontweight=('bold' if any_failed else 'normal'),
                horizontalalignment='center',
                verticalalignment='center',
                bbox=dict(facecolor='white', alpha=0.85, edgecolor='none', pad=0.2),
                zorder=10,
            )
        except Exception:
            pass

    # NOTE: per-link edge labels intentionally disabled; we only show multiplicity.

    # add a legend so the failed links are obvious to readers
    try:
        from matplotlib.lines import Line2D
        legend_handles = [
            Line2D([0], [0], color='gray', lw=2, label='healthy link'),
            Line2D([0], [0], color='red', lw=4, linestyle='--', label='failed link'),
        ]
        ax.legend(handles=legend_handles, loc='upper center', fontsize=max(8, int(base_font * 0.9)), frameon=True)
    except Exception:
        pass

    saved_path = None
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ver_index = 1
    # choose a non-colliding path
    while True:
        rel_path = os.path.join('results', f"topology_{topop_name}_{timestamp}_{ver_index}.png")
        if not os.path.exists(rel_path):
            break
        ver_index += 1
    try:
        # ensure results directory exists
        try:
            os.makedirs(os.path.dirname(rel_path) or '.', exist_ok=True)
        except Exception:
            pass
        # save using absolute path so opening the file doesn't depend on CWD
        saved_path = os.path.abspath(rel_path)
        try:
            fig.savefig(saved_path, bbox_inches='tight')
            logging.info(f"Topology saved to {saved_path}")
            # Intentionally do NOT open the saved image with an external viewer to avoid
            # blocking the application or creating side effects. The `show` parameter
            # is kept for API compatibility but is ignored here.
        except Exception as e:
            logging.info(f"Topology failed to save into {saved_path}: {e}")
            saved_path = None
    except Exception:
        saved_path = None

    # restore logging levels if they were modified
    try:
        if _logging is not None:
            for lname, prev in _prev_levels.items():
                try:
                    if prev is not None:
                        _logging.getLogger(lname).setLevel(prev)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        plt.close(fig)
    except Exception:
        try:
            plt.close()
        except Exception:
            pass
    return saved_path


def plot_hosts_received_histogram(hosts_received: Union[Dict[str, int], Sequence[int]], run_name: str,
                                  out_dir: str = 'results/experiments') -> Optional[str]:
    """Plot a histogram of how many messages each host received in a run.

    hosts_received: mapping host_name -> received_count
    run_name: short identifier for the run (used in filename)
    out_dir: directory to save the histogram
    Returns absolute path to saved file or None on failure.
    """
    try:
        import matplotlib as mpl
        mpl.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return None

    # Accept either a dict of {host: count} or a sequence of counts
    counts = []
    try:
        if hosts_received is None:
            counts = []
        elif isinstance(hosts_received, dict):
            counts = [int(v) for v in hosts_received.values()]
        else:
            # treat as sequence of numbers
            counts = [int(v) for v in hosts_received]
    except Exception:
        counts = []

    if not counts:
        # nothing to plot
        return None

    fig, ax = plt.subplots()
    ax.hist(counts, bins='auto', color='tab:blue', edgecolor='black')
    ax.set_xlabel('Number of messages received')
    ax.set_ylabel('Number of hosts')
    ax.set_title(f'Hosts received messages histogram: {run_name}')
    fig.tight_layout()

    safe_name = "".join(c if c.isalnum() or c in '._-' else '_' for c in str(run_name))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    out_path = os.path.join(out_dir, f"exp_{safe_name}_hosts_received_hist.png")
    try:
        fig.savefig(out_path)
    finally:
        try:
            plt.close(fig)
        except Exception:
            pass
    return os.path.abspath(out_path)
