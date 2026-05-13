"""SVG rendering backend for rosia diagrams."""

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from xml.sax.saxutils import escape

from rosia.time import Time
from rosia.diagram.constants import (
    SCALE,
    PADDING,
    ICON_SIZE,
    NODE_BORDER_WIDTH,
    PORT_TRIANGLE_SIZE,
    EDGE_WIDTH,
    INTERNAL_EDGE_WIDTH,
    HEADER_FONT_SIZE,
    PORT_FONT_SIZE,
    REACTION_FONT_SIZE,
    PORT_TEXT_PAD,
    CORNER_RADIUS,
    ARROWHEAD_LENGTH,
    ARROWHEAD_WIDTH,
    COLORS,
    ICON_NODES,
    NODE_PAD_H,
    REACTION_POINTINESS,
    REACTION_CHEVRON_HEIGHT,
    CHAR_WIDTH,
    REACTION_MIN_WIDTH,
)

if TYPE_CHECKING:
    from rosia.diagram.diagram import Graph, Node, Port, Edge, Reaction

ASSETS_DIR = Path(__file__).parent / "assets"

# Font stack for SVG text elements
_FONT_FAMILY = "Helvetica, Arial, sans-serif"


# ── Public API ──────────────────────────────────────────────────────────────


def render_graph_svg(graph: "Graph") -> Tuple[str, dict]:
    """Render a graph to an SVG string and return JSON position data."""
    y_offset = _compute_y_offset(graph)
    width, height = _compute_canvas_size(graph, y_offset)

    icons = {name: _load_icon_b64(name.lower()) for name in ICON_NODES}
    port_positions = _build_port_positions(graph, y_offset, icons)

    elements: List[str] = []

    # Defs for clip paths
    defs: List[str] = []
    for i, node in enumerate(graph.nodes):
        if node.node_type not in ICON_NODES or icons.get(node.node_type) is None:
            nx, ny = _to_screen(node.x, node.y, y_offset)
            nw, nh = node.width * SCALE, node.height * SCALE
            defs.append(
                f'<clipPath id="node-clip-{i}">'
                f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" '
                f'rx="{CORNER_RADIUS}" ry="{CORNER_RADIUS}"/>'
                f"</clipPath>"
            )

    # Draw nodes
    for i, node in enumerate(graph.nodes):
        elements.append(_svg_node(node, i, y_offset, icons))

    # Draw edges
    edge_json_list: List[dict] = []
    for edge in graph.edges:
        svg, points = _svg_edge(edge, port_positions, y_offset)
        elements.append(svg)
        edge_json_list.append(
            {
                "source_port": edge.source_port,
                "target_port": edge.target_port,
                "points": [{"x": round(px, 1), "y": round(py, 1)} for px, py in points],
            }
        )

    # Assemble SVG
    defs_str = "\n    ".join(defs)
    body = "\n  ".join(elements)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f"  <defs>\n    {defs_str}\n  </defs>\n"
        f'  <rect width="100%" height="100%" fill="{COLORS["background"]}"/>\n'
        f"  {body}\n"
        f"</svg>\n"
    )

    json_data = _build_json(graph, y_offset, port_positions, edge_json_list, icons)
    return svg, json_data


# ── Coordinate helpers (shared logic with renderer.py) ──────────────────────


def _to_screen(x: float, y: float, y_offset: float = 0) -> Tuple[float, float]:
    return x * SCALE + PADDING, (y + y_offset) * SCALE + PADDING


def _compute_y_offset(graph: "Graph") -> float:
    all_y = [n.y for n in graph.nodes]
    for edge in graph.edges:
        for _, by in edge.bend_points:
            all_y.append(by)
        for _, py in edge.full_route:
            all_y.append(py)
    min_y = min(all_y, default=0)
    return max(0, -min_y + 20)


def _compute_canvas_size(graph: "Graph", y_offset: float) -> Tuple[int, int]:
    all_x = [n.x + n.width for n in graph.nodes]
    all_y = [n.y + n.height for n in graph.nodes]
    for edge in graph.edges:
        for bx, by in edge.bend_points:
            all_x.append(bx)
            all_y.append(by)
        for px, py in edge.full_route:
            all_x.append(px)
            all_y.append(py)
    max_x = max(all_x, default=0)
    max_y = max(all_y, default=0)
    return int(max_x * SCALE + 2 * PADDING), int((max_y + y_offset + 20) * SCALE + 2 * PADDING)


def _load_icon_b64(name: str) -> Optional[str]:
    """Load a PNG icon and return a base64 data-URI string."""
    path = ASSETS_DIR / f"{name}.png"
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except Exception:
        return None


# ── Port positions ──────────────────────────────────────────────────────────


def _build_port_positions(graph: "Graph", y_offset: float, icons: dict) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    for node in graph.nodes:
        nx, ny = _to_screen(node.x, node.y, y_offset)
        nw = node.width * SCALE
        icon_config = ICON_NODES.get(node.node_type)
        is_icon = icon_config is not None and icons.get(node.node_type) is not None
        for port in node.ports:
            py = ny + port.y * SCALE
            if is_icon and icon_config is not None:
                conn_inset = icon_config.get("connection_inset", 0) * SCALE
                cx = nx + nw / 2
                px = cx - ICON_SIZE / 2 + conn_inset if port.is_input else cx + ICON_SIZE / 2 - conn_inset
            else:
                px = nx if port.is_input else nx + nw
            positions[port.id] = (px, py)
    return positions


# ── SVG node rendering ──────────────────────────────────────────────────────


def _svg_node(node: "Node", idx: int, y_offset: float, icons: dict) -> str:
    icon_config = ICON_NODES.get(node.node_type)
    icon_b64 = icons.get(node.node_type)
    if icon_config is not None and icon_b64 is not None:
        return _svg_icon_node(node, y_offset, icon_b64)
    return _svg_rect_node(node, idx, y_offset)


def _svg_icon_node(node: "Node", y_offset: float, icon_b64: str) -> str:
    nx, ny = _to_screen(node.x, node.y, y_offset)
    nw = node.width * SCALE
    port_y = node.ports[0].y * SCALE if node.ports else node.height * SCALE / 2
    ix = nx + nw / 2 - ICON_SIZE / 2
    iy = ny + port_y - ICON_SIZE / 2
    parts = [
        f'<image x="{ix}" y="{iy}" width="{ICON_SIZE}" height="{ICON_SIZE}" href="{icon_b64}"/>',
    ]
    if node.node_type == "Timer" and node.init_args:
        label = _get_timer_label(node.init_args)
        if label:
            tx = nx + nw / 2
            ty = iy + ICON_SIZE + 4 * SCALE + PORT_FONT_SIZE * 0.35
            parts.append(
                f'<text x="{tx}" y="{ty}" text-anchor="middle" '
                f'font-family="{_FONT_FAMILY}" font-size="{PORT_FONT_SIZE}" '
                f'fill="{COLORS["header_text"]}">{escape(label)}</text>'
            )
    return "\n  ".join(parts)


def _get_timer_label(init_args: Any) -> Optional[str]:
    if init_args.args:
        interval = init_args.args[0]
    elif "interval" in init_args.kwargs:
        interval = init_args.kwargs["interval"]
    else:
        return None
    if len(init_args.args) > 1:
        offset = init_args.args[1]
    elif "offset" in init_args.kwargs:
        offset = init_args.kwargs["offset"]
    else:
        offset = Time(0)
    return f"({offset},{interval})"


def _svg_rect_node(node: "Node", idx: int, y_offset: float) -> str:
    nx, ny = _to_screen(node.x, node.y, y_offset)
    nw = node.width * SCALE
    nh = node.height * SCALE
    header_h = node.header_height * SCALE
    bw = NODE_BORDER_WIDTH

    parts: List[str] = [f"<!-- {escape(node.name)} -->"]

    # Full node rounded rect
    parts.append(
        f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" '
        f'rx="{CORNER_RADIUS}" ry="{CORNER_RADIUS}" '
        f'fill="{COLORS["node_fill"]}" stroke="{COLORS["node_border"]}" '
        f'stroke-width="{bw}"/>'
    )

    # Header background (clipped to node shape)
    parts.append(
        f'<rect x="{nx + bw}" y="{ny + bw}" '
        f'width="{nw - 2 * bw}" height="{header_h - bw}" '
        f'fill="{COLORS["node_header_fill"]}" '
        f'clip-path="url(#node-clip-{idx})"/>'
    )

    # Separator line
    sep_y = ny + header_h
    parts.append(
        f'<line x1="{nx + bw}" y1="{sep_y}" x2="{nx + nw - bw}" y2="{sep_y}" '
        f'stroke="{COLORS["separator"]}" stroke-width="{max(SCALE, 1)}"/>'
    )

    # Header text
    tx = nx + nw / 2
    ty = ny + header_h / 2 + HEADER_FONT_SIZE * 0.35 - 2 * SCALE
    parts.append(
        f'<text x="{tx}" y="{ty}" text-anchor="middle" '
        f'font-family="{_FONT_FAMILY}" font-size="{HEADER_FONT_SIZE}" '
        f'font-weight="bold" fill="{COLORS["header_text"]}">'
        f"{escape(node.name)}</text>"
    )

    # Ports
    input_ports = [p for p in node.ports if p.is_input]
    output_ports = [p for p in node.ports if not p.is_input]
    for port in input_ports:
        parts.append(_svg_port(port, nx, ny, nw, is_input=True))
    for port in output_ports:
        parts.append(_svg_port(port, nx, ny, nw, is_input=False))

    # Reactions
    left_zone_end = nx + NODE_PAD_H * SCALE + _max_port_label_width(node, True) + PORT_TEXT_PAD
    right_zone_start = nx + nw - NODE_PAD_H * SCALE - _max_port_label_width(node, False) - PORT_TEXT_PAD
    if not input_ports:
        left_zone_end = nx + NODE_PAD_H * SCALE
    if not output_ports:
        right_zone_start = nx + nw - NODE_PAD_H * SCALE

    reaction_infos: List[Tuple[Any, Tuple[float, float, float, float]]] = []
    for reaction in node.reactions:
        svg, info = _svg_reaction(reaction, ny, left_zone_end, right_zone_start)
        parts.append(svg)
        reaction_infos.append((reaction, info))

    # Internal connections
    parts.append(_svg_internal_connections(node, nx, ny, nw, reaction_infos))

    return "\n  ".join(parts)


# ── Port SVG ────────────────────────────────────────────────────────────────


def _svg_port(port: "Port", node_x: float, node_y: float, node_w: float, is_input: bool) -> str:
    py = node_y + port.y * SCALE
    size = PORT_TRIANGLE_SIZE

    if is_input:
        px = node_x
        pts = f"{px - size * 0.3},{py - size} {px - size * 0.3},{py + size} {px + size * 0.7},{py}"
        text_x = px + PORT_TEXT_PAD
        anchor = "start"
    else:
        px = node_x + node_w
        pts = f"{px - size * 0.7},{py - size} {px - size * 0.7},{py + size} {px + size * 0.3},{py}"
        text_x = px - PORT_TEXT_PAD
        anchor = "end"

    return (
        f'<polygon points="{pts}" fill="{COLORS["port_fill"]}"/>'
        f'<text x="{text_x}" y="{py}" text-anchor="{anchor}" '
        f'dominant-baseline="middle" font-family="{_FONT_FAMILY}" '
        f'font-size="{PORT_FONT_SIZE}" fill="{COLORS["port_text"]}">'
        f"{escape(port.short_name)}</text>"
    )


# ── Reaction SVG ────────────────────────────────────────────────────────────


def _svg_reaction(
    reaction: "Reaction",
    node_y: float,
    zone_left: float,
    zone_right: float,
) -> Tuple[str, Tuple[float, float, float, float]]:
    pointiness = REACTION_POINTINESS * SCALE
    rh = REACTION_CHEVRON_HEIGHT * SCALE
    text_w = len(reaction.name) * CHAR_WIDTH * SCALE
    rw = max(text_w + 2 * pointiness + 12 * SCALE, REACTION_MIN_WIDTH * SCALE)

    zone_center = (zone_left + zone_right) / 2
    rx = zone_center - rw / 2
    ry = node_y + reaction.y * SCALE - rh / 2

    pts = (
        f"{rx + pointiness},{ry} "
        f"{rx + rw - pointiness},{ry} "
        f"{rx + rw},{ry + rh / 2} "
        f"{rx + rw - pointiness},{ry + rh} "
        f"{rx + pointiness},{ry + rh} "
        f"{rx},{ry + rh / 2}"
    )

    tx = rx + rw / 2
    ty = ry + rh / 2 + REACTION_FONT_SIZE * 0.35

    svg = (
        f'<polygon points="{pts}" fill="{COLORS["reaction_fill"]}" '
        f'stroke="{COLORS["reaction_border"]}"/>'
        f'<text x="{tx}" y="{ty}" text-anchor="middle" '
        f'font-family="{_FONT_FAMILY}" font-size="{REACTION_FONT_SIZE}" '
        f'fill="{COLORS["reaction_text"]}">{escape(reaction.name)}</text>'
    )
    return svg, (rx, ry, rw, rh)


# ── Internal connections SVG ────────────────────────────────────────────────


def _svg_internal_connections(
    node: "Node",
    node_x: float,
    node_y: float,
    node_w: float,
    reaction_infos: "List[Tuple[Any, Tuple[float, float, float, float]]]",
) -> str:
    port_screen_y = {p.id: node_y + p.y * SCALE for p in node.ports}
    color = COLORS["internal_edge"]
    lw = INTERNAL_EDGE_WIDTH
    lines: List[str] = []

    for reaction, (rx, ry, rw, rh) in reaction_infos:
        rlx, rly = rx, ry + rh / 2
        rrx, rry = rx + rw, ry + rh / 2

        for port_id in reaction.trigger_ports:
            if port_id in port_screen_y:
                py = port_screen_y[port_id]
                sx = node_x + PORT_TEXT_PAD + _port_label_width(node, port_id) + 4 * SCALE
                lines.append(f'<line x1="{sx}" y1="{py}" x2="{rlx}" y2="{rly}" stroke="{color}" stroke-width="{lw}"/>')

        for port_id in reaction.effect_ports:
            if port_id in port_screen_y:
                py = port_screen_y[port_id]
                ex = node_x + node_w - PORT_TEXT_PAD - _port_label_width(node, port_id) - 4 * SCALE
                lines.append(f'<line x1="{rrx}" y1="{rry}" x2="{ex}" y2="{py}" stroke="{color}" stroke-width="{lw}"/>')

    return "\n  ".join(lines)


def _max_port_label_width(node: "Node", is_input: bool) -> float:
    ports = [p for p in node.ports if p.is_input == is_input]
    if not ports:
        return 0
    return max(len(p.short_name) for p in ports) * CHAR_WIDTH * SCALE


def _port_label_width(node: "Node", port_id: str) -> float:
    for p in node.ports:
        if p.id == port_id:
            return len(p.short_name) * CHAR_WIDTH * SCALE
    return 0


# ── Edge SVG ────────────────────────────────────────────────────────────────


def _svg_edge(
    edge: "Edge",
    port_positions: Dict[str, Tuple[float, float]],
    y_offset: float,
) -> Tuple[str, List[Tuple[float, float]]]:
    """Render an edge as SVG. Returns (svg_string, point_list)."""
    src = port_positions.get(edge.source_port)
    tgt = port_positions.get(edge.target_port)
    if not src or not tgt:
        return "", []
    sx, sy = src
    tx, ty = tgt

    if edge.full_route:
        points = [_to_screen(px, py, y_offset) for px, py in edge.full_route]
        points = _optimize_route(points)
    else:
        scaled_bends = [_to_screen(bx, by, y_offset) for bx, by in edge.bend_points]
        points = _build_orthogonal_route(sx, sy, tx, ty, scaled_bends)

    parts: List[str] = []

    # Edge path with rounded corners. Physical connections render dashed.
    if len(points) >= 2:
        path_d = _rounded_polyline_path(points, radius=6 * SCALE)
        dash_attr = f' stroke-dasharray="{6 * SCALE} {4 * SCALE}"' if edge.is_physical else ""
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{COLORS["edge"]}" '
            f'stroke-width="{EDGE_WIDTH}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'
        )

    # Arrowhead
    if len(points) >= 2:
        parts.append(_svg_arrowhead(points[-2], points[-1]))

    # Delay label
    label = _format_delay_label(edge.delay)
    if label and len(points) >= 2:
        lx, ly, horizontal = _longest_segment_midpoint(points)
        if horizontal:
            tx_label = lx
            ty_label = ly - 4 * SCALE
            anchor = "middle"
        else:
            tx_label = lx + 4 * SCALE
            ty_label = ly
            anchor = "start"
        parts.append(
            f'<text x="{tx_label}" y="{ty_label}" text-anchor="{anchor}" '
            f'dominant-baseline="{"auto" if horizontal else "middle"}" '
            f'font-family="{_FONT_FAMILY}" font-size="{PORT_FONT_SIZE}" '
            f'fill="{COLORS["edge_label"]}">{escape(label)}</text>'
        )

    return "\n  ".join(parts), points


def _format_delay_label(delay: Optional["Time"]) -> str:
    """Format a delay for compact display on a diagram edge."""
    if delay is None:
        return ""
    if delay.value == 0 and delay.microstep == 0:
        return ""
    return f"delay = {delay}"


def _longest_segment_midpoint(points: List[Tuple[float, float]]) -> Tuple[float, float, bool]:
    """Return (x, y, is_horizontal) at the midpoint of the longest segment."""
    longest_len = -1.0
    longest_idx = 0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        seg_len = max(abs(x2 - x1), abs(y2 - y1))
        if seg_len > longest_len:
            longest_len = seg_len
            longest_idx = i
    x1, y1 = points[longest_idx]
    x2, y2 = points[longest_idx + 1]
    return (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1) >= abs(y2 - y1)


def _build_orthogonal_route(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    bends: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    if not bends:
        if abs(sy - ty) <= 1:
            return [(sx, sy), (tx, ty)]
        mx = (sx + tx) / 2
        return [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]

    points: List[Tuple[float, float]] = [(sx, sy)]
    cur_y = sy
    for i, (bx, by) in enumerate(bends):
        points.append((bx, cur_y))
        cur_y = ty if i == len(bends) - 1 else by
        points.append((bx, cur_y))
    points.append((tx, cur_y))
    return _optimize_route(points)


def _optimize_route(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(points) < 2:
        return points
    EPS = 2.0
    snapped: List[Tuple[float, float]] = [points[0]]
    for i in range(1, len(points)):
        px, py = snapped[-1]
        nx, ny = points[i]
        if abs(ny - py) < EPS:
            ny = py
        if abs(nx - px) < EPS:
            nx = px
        snapped.append((nx, ny))
    deduped: List[Tuple[float, float]] = [snapped[0]]
    for i in range(1, len(snapped)):
        px, py = deduped[-1]
        nx, ny = snapped[i]
        if abs(nx - px) > EPS or abs(ny - py) > EPS:
            deduped.append((nx, ny))
    if len(deduped) < 3:
        return deduped
    merged: List[Tuple[float, float]] = [deduped[0]]
    for i in range(1, len(deduped) - 1):
        ax, ay = merged[-1]
        bx, by = deduped[i]
        cx, cy = deduped[i + 1]
        same_h = abs(ay - by) < EPS and abs(by - cy) < EPS
        same_v = abs(ax - bx) < EPS and abs(bx - cx) < EPS
        if not (same_h or same_v):
            merged.append((bx, by))
    merged.append(deduped[-1])
    return merged


def _rounded_polyline_path(points: List[Tuple[float, float]], radius: float) -> str:
    """Build an SVG path `d` attribute for a polyline with rounded corners."""
    if len(points) < 2:
        return ""
    if len(points) == 2:
        return f"M{points[0][0]},{points[0][1]} L{points[1][0]},{points[1][1]}"

    parts: List[str] = [f"M{points[0][0]},{points[0][1]}"]

    for i in range(1, len(points) - 1):
        ax, ay = points[i - 1]
        bx, by = points[i]
        cx, cy = points[i + 1]

        seg1 = max(abs(bx - ax), abs(by - ay))
        seg2 = max(abs(cx - bx), abs(cy - by))
        r = min(radius, seg1 / 2, seg2 / 2)

        # Direction vectors
        d1x = 1 if bx > ax else (-1 if bx < ax else 0)
        d1y = 1 if by > ay else (-1 if by < ay else 0)
        d2x = 1 if cx > bx else (-1 if cx < bx else 0)
        d2y = 1 if cy > by else (-1 if cy < by else 0)

        # Points where the arc starts and ends
        sx = bx - d1x * r
        sy = by - d1y * r
        ex = bx + d2x * r
        ey = by + d2y * r

        # Determine sweep direction (clockwise or counter-clockwise)
        cross = d1x * d2y - d1y * d2x
        sweep = 1 if cross > 0 else 0

        parts.append(f"L{sx},{sy}")
        if r >= 2:
            parts.append(f"A{r},{r} 0 0 {sweep} {ex},{ey}")
        else:
            parts.append(f"L{ex},{ey}")

    parts.append(f"L{points[-1][0]},{points[-1][1]}")
    return " ".join(parts)


def _svg_arrowhead(from_pt: Tuple[float, float], to_pt: Tuple[float, float]) -> str:
    fx, fy = from_pt
    tx, ty = to_pt
    dx, dy = tx - fx, ty - fy
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1:
        return ""
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    al = ARROWHEAD_LENGTH
    aw = ARROWHEAD_WIDTH / 2
    pts = (
        f"{tx},{ty} {tx - ux * al + px * aw},{ty - uy * al + py * aw} {tx - ux * al - px * aw},{ty - uy * al - py * aw}"
    )
    return f'<polygon points="{pts}" fill="{COLORS["arrowhead"]}"/>'


# ── JSON builder ────────────────────────────────────────────────────────────


def _build_json(
    graph: "Graph",
    y_offset: float,
    port_positions: Dict[str, Tuple[float, float]],
    edge_json_list: List[dict],
    icons: dict,
) -> dict:
    nodes_json = []
    for node in graph.nodes:
        sx, sy = _to_screen(node.x, node.y, y_offset)
        sw, sh = node.width * SCALE, node.height * SCALE
        ports_json = [
            {
                "id": p.id,
                "name": p.short_name,
                "is_input": p.is_input,
                "x": round(port_positions.get(p.id, (0, 0))[0], 1),
                "y": round(port_positions.get(p.id, (0, 0))[1], 1),
            }
            for p in node.ports
        ]
        reactions_json = []
        for r in node.reactions:
            rh = REACTION_CHEVRON_HEIGHT * SCALE
            ry = sy + r.y * SCALE - rh / 2
            text_w = len(r.name) * CHAR_WIDTH * SCALE
            pointiness = REACTION_POINTINESS * SCALE
            rw = max(text_w + 2 * pointiness + 12 * SCALE, REACTION_MIN_WIDTH * SCALE)
            rx = sx + sw / 2 - rw / 2
            reactions_json.append(
                {
                    "name": r.name,
                    "x": round(rx, 1),
                    "y": round(ry, 1),
                    "width": round(rw, 1),
                    "height": round(rh, 1),
                    "trigger_ports": r.trigger_ports,
                    "effect_ports": r.effect_ports,
                }
            )
        nodes_json.append(
            {
                "id": node.id,
                "name": node.name,
                "type": node.node_type,
                "x": round(sx, 1),
                "y": round(sy, 1),
                "width": round(sw, 1),
                "height": round(sh, 1),
                "ports": ports_json,
                "reactions": reactions_json,
            }
        )
    return {"nodes": nodes_json, "edges": edge_json_list}
