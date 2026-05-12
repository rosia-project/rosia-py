"""Graph building and layout for rosia node visualization."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
import json

from pyelk import ELK  # pyright: ignore[reportMissingImports]

from rosia.diagram.constants import (
    CHAR_WIDTH,
    CHAR_WIDTH_HEADER,
    HEADER_HEIGHT,
    ROW_HEIGHT,
    NODE_BODY_PAD_TOP,
    NODE_BODY_PAD_BOTTOM,
    NODE_PAD_H,
    MIN_NODE_WIDTH,
    MIN_NODE_HEIGHT,
    ICON_NODES,
    PORT_TRI_SIZE,
    PORT_LABEL_GAP,
    REACTION_GAP_H,
    REACTION_MIN_WIDTH,
    REACTION_POINTINESS,
)
from rosia.diagram.renderer import render_graph
from rosia.diagram.svg_renderer import render_graph_svg
from rosia.frontend.Annotators import analyze_output_ports
import rosia

if TYPE_CHECKING:
    from rosia.coordinate.Application import NodeRuntimeInfo
    from rosia.time import Time


@dataclass
class Port:
    id: str
    short_name: str
    is_input: bool
    y: float = 0  # relative Y center within node (logical units)


@dataclass
class Reaction:
    name: str
    trigger_ports: List[str]  # IDs of input ports that trigger this reaction
    effect_ports: List[str]  # IDs of output ports this reaction writes to
    y: float = 0  # relative Y center within node (logical units)


@dataclass
class Node:
    id: str
    name: str
    node_type: str
    ports: List[Port]
    reactions: List[Reaction] = field(default_factory=list)
    init_args: Optional[object] = None
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    header_height: float = HEADER_HEIGHT


@dataclass
class Edge:
    source_port: str
    target_port: str
    delay: "Optional[Time] | int" = None
    is_physical: bool = False
    bend_points: List[Tuple[float, float]] = field(default_factory=list)
    # Full orthogonal route in logical coords, if a post-processor (e.g.
    # ``_avoid_node_body_crossings``) has rewritten the edge to avoid drawing
    # through node interiors. When set, the renderer uses these points
    # directly instead of reconstructing them from ``bend_points``.
    full_route: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class Graph:
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)


def diagram(
    node_infos: "Dict[str, NodeRuntimeInfo]",
    save_to: Optional[str] = None,
    rerun: bool = False,
    save_json: bool = False,
) -> None:
    """Main entry point: build graph, layout with ELK, and render."""
    if not node_infos:
        return

    graph = build_graph(node_infos)
    layout_graph(graph)

    is_svg = save_to is not None and save_to.lower().endswith(".svg")

    if is_svg:
        svg_str, json_data = render_graph_svg(graph)
    else:
        image, json_data = render_graph(graph)

    if save_to:
        if is_svg:
            with open(save_to, "w") as f:
                f.write(svg_str)
        else:
            image.save(save_to)
        if save_json:
            json_path = save_to.rsplit(".", 1)[0] + ".json"
            with open(json_path, "w") as f:
                json.dump(json_data, f, indent=2)

    if rerun:
        if not is_svg:
            rosia.rerun_manager.send_blueprint()
            rosia.rerun_manager.render_diagram(image)


def build_graph(node_infos: "Dict[str, NodeRuntimeInfo]") -> Graph:
    """Convert node runtime info to graph representation."""
    graph = Graph()

    for node_name, node_info in node_infos.items():
        runtime = node_info.node
        node_type = runtime.node_cls.__name__.replace("NodeRuntime", "")

        init_args = None
        if hasattr(runtime.node_cls, "_rosia_annotations"):
            init_args = runtime.node_cls._rosia_annotations.get("init_args")

        # Build ports
        ports: List[Port] = []
        for port_name in runtime.input_port_connectors:
            short_name = port_name.split(".", 1)[1]
            ports.append(Port(id=port_name, short_name=short_name, is_input=True))

        for port_name in runtime.output_port_connectors:
            short_name = port_name.split(".", 1)[1]
            ports.append(Port(id=port_name, short_name=short_name, is_input=False))

        # Extract reactions
        reactions = _extract_reactions(runtime, node_name)

        # Compute node size and internal layout positions
        width, height = _compute_node_layout(node_name, ports, reactions, node_type)

        graph.nodes.append(
            Node(
                id=node_name,
                name=node_name,
                node_type=node_type,
                ports=ports,
                reactions=reactions,
                init_args=init_args,
                width=width,
                height=height,
            )
        )

        # Build edges from output→downstream connections
        for port_name, connector in runtime.output_port_connectors.items():
            for downstream, is_physical, delay in connector.downstream_ports:
                graph.edges.append(
                    Edge(
                        source_port=port_name,
                        target_port=downstream.name,
                        delay=delay,
                        is_physical=is_physical,
                    )
                )

    return graph


def _extract_reactions(runtime: Any, node_name: str) -> List[Reaction]:
    """Extract unique reactions from a node's input port connectors."""
    reactions_by_name: Dict[str, Reaction] = {}

    # Detect start() on the original user class
    original_cls = None
    if hasattr(runtime.node_cls, "_rosia_annotations"):
        original_cls = runtime.node_cls._rosia_annotations.get("original_cls")
    if original_cls is not None and hasattr(original_cls, "start"):
        start_func = original_cls.start
        effect_port_ids: List[str] = []
        try:
            output_port_names = analyze_output_ports(start_func)
            for op_name in output_port_names:
                full_name = f"{node_name}.{op_name}"
                if full_name in runtime.output_port_connectors:
                    if full_name not in effect_port_ids:
                        effect_port_ids.append(full_name)
        except Exception:
            pass
        reactions_by_name["start"] = Reaction(
            name="start",
            trigger_ports=[],
            effect_ports=effect_port_ids,
        )

    for port_name, connector in runtime.input_port_connectors.items():
        for func in connector.trigger_functions:
            fname = func.__name__
            if fname not in reactions_by_name:
                # Use AST analysis to get precise output ports for this reaction
                effect_port_ids = []
                try:
                    output_port_names = analyze_output_ports(func)
                    for op_name in output_port_names:
                        full_name = f"{node_name}.{op_name}"
                        if full_name in runtime.output_port_connectors:
                            if full_name not in effect_port_ids:
                                effect_port_ids.append(full_name)
                except Exception:
                    # Fallback: use affected_output_ports from the connector
                    for op in connector.affected_output_ports:
                        if op.name not in effect_port_ids:
                            effect_port_ids.append(op.name)

                reactions_by_name[fname] = Reaction(
                    name=fname,
                    trigger_ports=[],
                    effect_ports=effect_port_ids,
                )
            if port_name not in reactions_by_name[fname].trigger_ports:
                reactions_by_name[fname].trigger_ports.append(port_name)

    return list(reactions_by_name.values())


def _distribute_y(count: int, body_start: float, body_height: float) -> List[float]:
    """Distribute `count` items vertically, centered in body area."""
    if count == 0:
        return []
    spacing = body_height / count
    return [body_start + (i + 0.5) * spacing for i in range(count)]


def _compute_node_layout(
    name: str,
    ports: List[Port],
    reactions: List[Reaction],
    node_type: str,
) -> Tuple[float, float]:
    """Compute node size and assign Y positions to ports and reactions."""
    input_ports = [p for p in ports if p.is_input]
    output_ports = [p for p in ports if not p.is_input]

    is_icon_node = node_type in ICON_NODES
    if is_icon_node:
        icon_config = ICON_NODES[node_type]
        width = icon_config.get("width", MIN_NODE_WIDTH)
        n_ports = max(len(input_ports), len(output_ports), 1)
        height = n_ports * ROW_HEIGHT + 40
        # Distribute port Y positions for icon nodes
        for i, p in enumerate(input_ports):
            p.y = (i + 0.5) * height / max(len(input_ports), 1)
        for i, p in enumerate(output_ports):
            p.y = (i + 0.5) * height / max(len(output_ports), 1)
        return width, max(height, MIN_NODE_HEIGHT)

    # Number of rows in the body
    n_rows = max(len(input_ports), len(reactions), len(output_ports), 1)

    # Height
    header_h = HEADER_HEIGHT
    body_h = NODE_BODY_PAD_TOP + n_rows * ROW_HEIGHT + NODE_BODY_PAD_BOTTOM
    height = header_h + body_h

    # Width computation
    max_in_label = max((len(p.short_name) for p in input_ports), default=0)
    max_out_label = max((len(p.short_name) for p in output_ports), default=0)
    max_reaction_label = max((len(r.name) for r in reactions), default=0)

    # Header width
    name_width = len(name) * CHAR_WIDTH_HEADER + 2 * NODE_PAD_H

    # Body width: port_tri + gap + label + reaction_gap + reaction + reaction_gap + label + gap + port_tri + padding
    left_w = PORT_TRI_SIZE + PORT_LABEL_GAP + max_in_label * CHAR_WIDTH if input_ports else 0
    right_w = max_out_label * CHAR_WIDTH + PORT_LABEL_GAP + PORT_TRI_SIZE if output_ports else 0
    reaction_w = (
        max(
            max_reaction_label * CHAR_WIDTH + 2 * REACTION_POINTINESS + 16,
            REACTION_MIN_WIDTH,
        )
        if reactions
        else 0
    )
    gap_left = REACTION_GAP_H if (input_ports and reactions) else 0
    gap_right = REACTION_GAP_H if (output_ports and reactions) else 0
    content_width = left_w + gap_left + reaction_w + gap_right + right_w + 2 * NODE_PAD_H

    width = max(name_width, content_width, MIN_NODE_WIDTH)
    height = max(height, MIN_NODE_HEIGHT)

    # Assign Y positions to ports and reactions within the node
    body_start = header_h + NODE_BODY_PAD_TOP
    body_content_h = n_rows * ROW_HEIGHT

    in_ys = _distribute_y(len(input_ports), body_start, body_content_h)
    out_ys = _distribute_y(len(output_ports), body_start, body_content_h)
    react_ys = _distribute_y(len(reactions), body_start, body_content_h)

    for i, p in enumerate(input_ports):
        p.y = in_ys[i]
    for i, p in enumerate(output_ports):
        p.y = out_ys[i]
    for i, r in enumerate(reactions):
        r.y = react_ys[i]

    return width, height


def layout_graph(graph: Graph) -> None:
    """Use ELK to compute node and port positions (edges routed orthogonally)."""
    elk_children = []
    for node in graph.nodes:
        elk_ports = []
        for p in node.ports:
            elk_ports.append(
                {
                    "id": p.id,
                    "width": 8,
                    "height": 8,
                    "x": 0 if p.is_input else node.width - 8,
                    "y": p.y - 4,  # center the port marker on the Y position
                    "layoutOptions": {
                        "elk.port.side": "WEST" if p.is_input else "EAST",
                    },
                }
            )
        elk_children.append(
            {
                "id": node.id,
                "width": node.width,
                "height": node.height,
                "ports": elk_ports,
                "layoutOptions": {"elk.portConstraints": "FIXED_POS"},
            }
        )

    elk_edges = [
        {"id": f"e{i}", "sources": [e.source_port], "targets": [e.target_port]} for i, e in enumerate(graph.edges)
    ]

    elk_graph = {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.spacing.nodeNode": "50",
            "elk.layered.spacing.nodeNodeBetweenLayers": "100",
            "elk.spacing.edgeEdge": "25",
            "elk.spacing.edgeNode": "25",
            "elk.layered.spacing.edgeEdgeBetweenLayers": "25",
            "elk.layered.spacing.edgeNodeBetweenLayers": "25",
            "elk.edgeRouting": "ORTHOGONAL",
        },
        "children": elk_children,
        "edges": elk_edges,
    }

    result = ELK().layout(elk_graph)

    # Copy positions back
    node_map = {n.id: n for n in graph.nodes}
    for elk_node in result.get("children", []):
        node = node_map.get(elk_node["id"])
        if node:
            node.x = elk_node["x"]
            node.y = elk_node["y"]

    # Extract only intermediate bend points from ELK (not start/end).
    # Start/end are derived from our own port positions during rendering,
    # which ensures edges connect exactly to drawn ports.
    edge_map = {f"e{i}": e for i, e in enumerate(graph.edges)}
    for elk_edge in result.get("edges", []):
        edge = edge_map.get(elk_edge["id"])
        if edge:
            for section in elk_edge.get("sections", []):
                bend_points: List[Tuple[float, float]] = []
                for bp in section.get("bendPoints", []):
                    bend_points.append((bp["x"], bp["y"]))
                edge.bend_points = bend_points

    _reroute_self_loops(graph)
    _spread_vertical_segments(graph)
    _avoid_node_body_crossings(graph)


# Padding between a self-loop route and the node it wraps (logical units).
SELF_LOOP_PAD = 30.0


def _reroute_self_loops(graph: Graph) -> None:
    """Re-route self-loop edges so they wrap over the top of their node
    instead of crossing through the node body (ELK's default for self-loops)."""
    port_to_node: Dict[str, Node] = {}
    for node in graph.nodes:
        for port in node.ports:
            port_to_node[port.id] = node

    # Group self-loops by node so we can stack them at different heights.
    loops_by_node: Dict[str, List[Edge]] = {}
    for edge in graph.edges:
        src = port_to_node.get(edge.source_port)
        tgt = port_to_node.get(edge.target_port)
        if src is not None and src is tgt:
            loops_by_node.setdefault(src.id, []).append(edge)

    for node_id, edges in loops_by_node.items():
        node = next(n for n in graph.nodes if n.id == node_id)
        for i, edge in enumerate(edges):
            offset = i * MIN_EDGE_SPACING
            rx = node.x + node.width + SELF_LOOP_PAD + offset
            lx = node.x - SELF_LOOP_PAD - offset
            above_y = node.y - SELF_LOOP_PAD - offset
            edge.bend_points = [(rx, above_y), (lx, above_y)]


# Minimum logical distance between vertical edge corridors in the same gap.
MIN_EDGE_SPACING = 20.0


def _spread_vertical_segments(graph: Graph) -> None:
    """Ensure vertical segments of different edges in the same inter-node gap
    are spaced apart by at least MIN_EDGE_SPACING.

    Groups bend points by which inter-layer gap they fall into, then spreads
    them evenly if they are too close together.
    """
    if not graph.edges:
        return

    # Build sorted list of node x-intervals: [(left, right), ...]
    node_intervals = sorted([(n.x, n.x + n.width) for n in graph.nodes], key=lambda iv: iv[0])

    # For each edge with bend points, collect (bend_x, edge_index, bp_index)
    # grouped by which gap they fall into.
    gaps: Dict[int, List[Tuple[float, int, int]]] = {}  # gap_index -> entries

    for ei, edge in enumerate(graph.edges):
        for bi, (bx, by) in enumerate(edge.bend_points):
            # Find which gap this bend falls into
            gap_idx = _find_gap(bx, node_intervals)
            if gap_idx not in gaps:
                gaps[gap_idx] = []
            gaps[gap_idx].append((bx, ei, bi))

    # For each gap, spread the bend x-coordinates if too close
    for gap_idx, entries in gaps.items():
        if len(entries) < 2:
            continue

        # Sort by current x
        entries.sort(key=lambda e: e[0])

        # Check if any pair is closer than MIN_EDGE_SPACING
        needs_spread = False
        for i in range(1, len(entries)):
            if entries[i][0] - entries[i - 1][0] < MIN_EDGE_SPACING:
                needs_spread = True
                break

        if not needs_spread:
            continue

        # Get gap boundaries
        gap_left, gap_right = _gap_bounds(gap_idx, node_intervals)
        gap_width = gap_right - gap_left

        # Evenly distribute the bend x-coords within the gap
        n = len(entries)
        spacing = gap_width / (n + 1)
        for i, (old_bx, ei, bi) in enumerate(entries):
            new_bx = gap_left + (i + 1) * spacing
            bx_old, by_old = graph.edges[ei].bend_points[bi]
            graph.edges[ei].bend_points[bi] = (new_bx, by_old)


# Margin (logical units) between a re-routed edge and the node body it skirts.
NODE_AVOID_MARGIN = 20.0


def _safe_v_x(
    x_orig: float,
    y_a: float,
    y_b: float,
    nodes: List[Node],
    eps: float = 0.5,
) -> float:
    """Return an x near ``x_orig`` where a vertical from ``y_a`` to ``y_b``
    doesn't pass through any node's interior.

    Used by :func:`_avoid_node_body_crossings` when stitching in detour
    bends: the V at the detour's bookend can otherwise sit inside the
    source/target node's body if the H segment started or ended on that
    node's port edge.
    """
    y_lo = min(y_a, y_b) + eps
    y_hi = max(y_a, y_b) - eps
    candidate = x_orig
    for _ in range(10):  # bounded outward search
        blocker: Optional[Node] = None
        for n in nodes:
            if not (n.x + eps < candidate < n.x + n.width - eps):
                continue  # candidate already outside this node's x interior
            if y_hi <= n.y or y_lo >= n.y + n.height:
                continue  # V doesn't intersect node's y span
            blocker = n
            break
        if blocker is None:
            return candidate
        left = blocker.x - NODE_AVOID_MARGIN
        right = blocker.x + blocker.width + NODE_AVOID_MARGIN
        candidate = left if abs(candidate - left) <= abs(candidate - right) else right
    return candidate


def _avoid_node_body_crossings(graph: Graph) -> None:
    """Reroute edges whose orthogonal segments pass through node interiors.

    ELK + ``_spread_vertical_segments`` can leave us with bend points that,
    when expanded into a strict H/V/H/V/... route, place horizontal segments
    at y-coordinates inside other nodes' bodies. The renderer then draws
    those segments straight through the node, producing the visual overlap
    that prompted this fix.

    For each edge we:
      1. Reconstruct the full orthogonal route from ``bend_points`` using the
         same logic as :func:`rosia.diagram.renderer._build_orthogonal_route`.
      2. Walk the segments. If a horizontal segment passes through a
         non-source / non-target node interior, replace it with a detour
         that goes above or below all blockers (whichever is closer).
      3. If anything changed, store the result on ``edge.full_route`` so the
         renderer skips bend reconstruction.
    """
    if not graph.edges:
        return

    port_pos: Dict[str, Tuple[float, float]] = {}
    port_to_node: Dict[str, Node] = {}
    for node in graph.nodes:
        for port in node.ports:
            x = node.x + (0 if port.is_input else node.width)
            y = node.y + port.y
            port_pos[port.id] = (x, y)
            port_to_node[port.id] = node

    for edge in graph.edges:
        src = port_pos.get(edge.source_port)
        tgt = port_pos.get(edge.target_port)
        if src is None or tgt is None:
            continue
        src_node = port_to_node.get(edge.source_port)
        tgt_node = port_to_node.get(edge.target_port)

        route = _expand_route(src, tgt, edge.bend_points)
        if not _route_has_node_overlap(route, graph.nodes):
            continue  # ELK got it right — leave bend_points as-is

        # First try a clean global wrap — a single detour y above (or below)
        # *all* nodes, with verticals descending from the source/target ports
        # to the wrap corridor. For typical back-edges this produces a clean
        # 6-point route instead of the zig-zag the per-segment detour
        # algorithm leaves.
        wrap = _wrap_around_route(src, tgt, graph.nodes, src_node=src_node, tgt_node=tgt_node)
        if wrap is not None and not _route_has_node_overlap(wrap, graph.nodes):
            edge.full_route = wrap
            continue

        # Fallback: per-segment detour around each blocker.
        new_route = _detour_route(route, graph.nodes, src_node, tgt_node)
        if new_route != route:
            edge.full_route = new_route


def _expand_route(
    src: Tuple[float, float],
    tgt: Tuple[float, float],
    bends: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """Reproduce the strictly-orthogonal route the renderer builds from bends.

    Mirrors :func:`rosia.diagram.renderer._build_orthogonal_route` but in
    logical coordinates so we can analyse + rewrite it before scaling.
    """
    sx, sy = src
    tx, ty = tgt
    if not bends:
        if abs(sy - ty) <= 1:
            return [(sx, sy), (tx, ty)]
        mx = (sx + tx) / 2.0
        return [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]

    points: List[Tuple[float, float]] = [(sx, sy)]
    cur_y = sy
    for i, (bx, by) in enumerate(bends):
        is_last = i == len(bends) - 1
        points.append((bx, cur_y))
        cur_y = ty if is_last else by
        points.append((bx, cur_y))
    points.append((tx, cur_y))
    return points


def _route_has_node_overlap(
    points: List[Tuple[float, float]],
    nodes: List[Node],
    eps: float = 0.5,
) -> bool:
    """True if any segment of ``points`` passes through a node *interior*."""
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        for n in nodes:
            if abs(y1 - y2) < eps:  # horizontal
                if not (n.y + eps < y1 < n.y + n.height - eps):
                    continue
                lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                if hi - eps <= n.x or lo + eps >= n.x + n.width:
                    continue
                inside_lo = max(lo, n.x + eps)
                inside_hi = min(hi, n.x + n.width - eps)
                if inside_hi - inside_lo > eps:
                    return True
            elif abs(x1 - x2) < eps:  # vertical
                if not (n.x + eps < x1 < n.x + n.width - eps):
                    continue
                lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                if hi - eps <= n.y or lo + eps >= n.y + n.height:
                    continue
                inside_lo = max(lo, n.y + eps)
                inside_hi = min(hi, n.y + n.height - eps)
                if inside_hi - inside_lo > eps:
                    return True
    return False


def _wrap_around_route(
    src: Tuple[float, float],
    tgt: Tuple[float, float],
    nodes: List[Node],
    *,
    src_node: "Optional[Node]" = None,
    tgt_node: "Optional[Node]" = None,
) -> Optional[List[Tuple[float, float]]]:
    """Build a clean detour that wraps above or below *all* nodes.

    Includes short horizontal stubs at each port so the edge exits/enters
    the port body horizontally — otherwise a vertical drawn at exactly
    ``node.x`` or ``node.x + node.width`` slides along the node's border.
    Tried before the per-segment detour fallback so that long back-edges
    don't accumulate zig-zag bends they don't need.
    """
    if not nodes:
        return None
    sx, sy = src
    tx, ty = tgt
    above = min(n.y for n in nodes) - NODE_AVOID_MARGIN
    below = max(n.y + n.height for n in nodes) + NODE_AVOID_MARGIN
    mid_y = (sy + ty) / 2.0

    src_dir = _port_stub_direction(sx, src_node)
    tgt_dir = _port_stub_direction(tx, tgt_node)
    stub = NODE_AVOID_MARGIN
    sx_off = sx + src_dir * stub
    tx_off = tx + tgt_dir * stub

    # Try the closer corridor first; fall back to the other if the first
    # somehow still clips a node (rare — only if a node spans extreme y).
    options = sorted([above, below], key=lambda y: abs(mid_y - y))
    for clear_y in options:
        route = [
            (sx, sy),
            (sx_off, sy),
            (sx_off, clear_y),
            (tx_off, clear_y),
            (tx_off, ty),
            (tx, ty),
        ]
        if not _route_has_node_overlap(route, nodes):
            return route
    return None


def _port_stub_direction(port_x: float, node: "Optional[Node]") -> int:
    """+1 if the port sits on the node's EAST edge, -1 for WEST.

    Used so the wrap-around detour leaves an EAST output going right and
    approaches a WEST input from the left. Defaults to +1 when the host
    node isn't known.
    """
    if node is None:
        return 1
    center_x = node.x + node.width / 2.0
    return 1 if port_x >= center_x else -1


def _detour_route(
    route: List[Tuple[float, float]],
    nodes: List[Node],
    src_node: "Optional[Node]",
    tgt_node: "Optional[Node]",
) -> List[Tuple[float, float]]:
    """Insert detour points around any H segment that crosses a node body.

    A segment is considered "crossing" if its y is *strictly* inside a
    node's vertical span and its x-extent overlaps the node's x-extent by
    more than ``EPS``. The endpoints' own source/target nodes are still
    checked: a long horizontal at the port's y can pass through the host
    node's body, which is the headline bug we fix here.
    """
    EPS = 0.5
    out = list(route)

    safety = 0
    while safety < 64:
        safety += 1
        changed = False
        i = 0
        while i < len(out) - 1:
            x1, y1 = out[i]
            x2, y2 = out[i + 1]
            if abs(y1 - y2) > EPS:
                i += 1
                continue
            xlo = min(x1, x2)
            xhi = max(x1, x2)

            blockers: List[Node] = []
            for n in nodes:
                # An H segment "crosses" node n's interior if y is strictly
                # inside its vertical band and its x-extent overlaps n's
                # x-extent by more than EPS on each side.
                if not (n.y + EPS < y1 < n.y + n.height - EPS):
                    continue
                if xhi - EPS <= n.x or xlo + EPS >= n.x + n.width:
                    continue
                # Allow exact-edge contact at a port boundary: e.g. a segment
                # whose endpoint sits on n.x (WEST port) doesn't count as a
                # crossing if the rest of the segment is OUTSIDE the node.
                seg_inside_lo = max(xlo, n.x + EPS)
                seg_inside_hi = min(xhi, n.x + n.width - EPS)
                if seg_inside_hi - seg_inside_lo <= EPS:
                    continue
                blockers.append(n)

            if not blockers:
                i += 1
                continue

            above = min(b.y for b in blockers) - NODE_AVOID_MARGIN
            below = max(b.y + b.height for b in blockers) + NODE_AVOID_MARGIN
            detour_y = above if abs(y1 - above) <= abs(y1 - below) else below

            # If x1 or x2 sits inside a node's x-extent, the inserted V
            # would still draw through that node's body. Shift x1/x2
            # outward to a clearance gap before stitching the detour in.
            x1_safe = _safe_v_x(x1, y1, detour_y, nodes)
            x2_safe = _safe_v_x(x2, y1, detour_y, nodes)

            spliced: List[Tuple[float, float]] = []
            if abs(x1_safe - x1) > EPS:
                spliced.append((x1_safe, y1))
            spliced.append((x1_safe, detour_y))
            spliced.append((x2_safe, detour_y))
            if abs(x2_safe - x2) > EPS:
                spliced.append((x2_safe, y1))

            out = out[: i + 1] + spliced + out[i + 1 :]
            changed = True
            i += 1 + len(spliced)  # skip past the inserted detour

        if not changed:
            break

    return out


def _find_gap(x: float, intervals: List[Tuple[float, float]]) -> int:
    """Find which inter-node gap an x-coordinate falls into.
    Returns gap index (0 = before first node, 1 = between node 0 and 1, etc.)."""
    for i, (left, right) in enumerate(intervals):
        if x < left:
            return i
    return len(intervals)


def _gap_bounds(gap_idx: int, intervals: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Get the (left, right) x-bounds of a gap between nodes."""
    if gap_idx == 0:
        left = 0
    else:
        left = intervals[gap_idx - 1][1]  # right edge of previous node

    if gap_idx >= len(intervals):
        right = intervals[-1][1] + 100  # past the last node
    else:
        right = intervals[gap_idx][0]  # left edge of next node

    return left, right
