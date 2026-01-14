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
    G = nx.Graph()
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

    # Add edges from Link objects (they hold node1/node2 references)
    for name, ent in entities.items():
        if ent is None:
            continue
        if hasattr(ent, "node1") and hasattr(ent, "node2"):
            n1 = getattr(ent.node1, "name", None)
            n2 = getattr(ent.node2, "name", None)
            if n1 and n2:
                # Use simple edge label (link name). Port annotations removed for readability.
                G.add_edge(n1, n2, label=name, _link_name=name)

    if G.number_of_nodes() == 0:
        print("No nodes to visualize in the topology.")
        return None

    # Prefer a layered tree-like layout (core -> aggregation -> edge -> hosts) when node naming follows
    # the fat-tree conventions. Otherwise fall back to graphviz or spring layout.
    layers = []  # initialize so it's available for sizing even if classification fails
    try:
        # classify nodes by name prefixes commonly used in fat-tree creator
        cores = sorted([n for n in G.nodes() if str(n).startswith('core_switch')])
        aggs = sorted([n for n in G.nodes() if str(n).startswith('agg_switch')])
        edges = sorted([n for n in G.nodes() if str(n).startswith('edge_switch')])
        hosts = sorted([n for n in G.nodes() if str(n).startswith('host')])

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

    # Color edges based on whether the underlying Link object is failed
    edge_colors = []
    edge_styles = []
    failed_edge_pairs = []
    healthy_edge_pairs = []
    for (u, v, data) in G.edges(data=True):
        link_name = data.get('label') or data.get('_link_name')
        link_obj = entities.get(link_name)
        if link_obj is not None and getattr(link_obj, 'failed', False):
            edge_colors.append('red')
            edge_styles.append('dashed')
            failed_edge_pairs.append((u, v, link_name))
        else:
            edge_colors.append('gray')
            edge_styles.append('solid')
            healthy_edge_pairs.append((u, v, link_name))

    # draw edges with styles; draw failed edges with a thicker line so they're more visible
    # first draw healthy (thin) then failed (thicker) so failed stand out
    for (u, v, link_name) in healthy_edge_pairs:
        coll = nx.draw_networkx_edges(G, pos, edgelist=[(u, v)], edge_color='gray', style='solid', width=1.5, alpha=0.9,
                                      ax=ax)
        try:
            coll.set_zorder(1)
        except Exception:
            pass
    for (u, v, link_name) in failed_edge_pairs:
        coll = nx.draw_networkx_edges(G, pos, edgelist=[(u, v)], edge_color='red', style='dashed', width=6.0,
                                      alpha=0.95, ax=ax)
        try:
            coll.set_zorder(5)
        except Exception:
            pass

    # draw edge labels afterwards
    edge_labels = nx.get_edge_attributes(G, 'label')
    # draw labels manually so we can color failed-link labels differently and avoid overlap
    for (u, v, data) in G.edges(data=True):
        label = data.get('label')
        if label is None:
            continue
        # compute midpoint for label placement
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        lx, ly = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        # choose color based on link failure
        link_obj = entities.get(label)
        is_failed = (link_obj is not None and getattr(link_obj, 'failed', False))
        lab_color = 'red' if is_failed else 'black'
        lab_text = (f"{label} (FAILED)" if is_failed else label)
        try:
            # draw marker for failed links to make them unmistakable
            if is_failed:
                try:
                    ax.scatter([lx], [ly], color='red', marker='x', s=80, zorder=4)
                except Exception:
                    pass
            ax.text(lx, ly, str(lab_text), fontsize=max(6, int(base_font * (1.0 if not is_failed else 1.1))),
                    color=lab_color, fontweight=('bold' if is_failed else 'normal'),
                    horizontalalignment='center', verticalalignment='center',
                    bbox=dict(facecolor='white', alpha=0.9, edgecolor='none', pad=0.3))
        except Exception:
            # fallback to networkx label drawing for this label
            pass

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
