"""Rendering logic for drawing LF-inspired diagrams to PIL images."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

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


# ── Public API ──────────────────────────────────────────────────────────────


def render_graph(graph: "Graph") -> Tuple[Image.Image, dict]:
    """Render a graph to a PIL Image and return JSON position data.

    Returns (image, json_data) where json_data contains node/edge positions.
    """
    y_offset = _compute_y_offset(graph)
    width, height = _compute_canvas_size(graph, y_offset)

    img = Image.new("RGB", (width, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    fonts = _load_fonts()
    icons = {name: _load_icon(name.lower()) for name in ICON_NODES}

    # Build port screen positions (needed for edge drawing)
    port_positions = _build_port_positions(graph, y_offset, icons)

    # Draw nodes
    for node in graph.nodes:
        _draw_node(img, draw, node, y_offset, fonts, icons)

    # Draw external edges and collect edge JSON
    edge_json_list = []
    for edge in graph.edges:
        points = _draw_edge(draw, edge, port_positions, y_offset, fonts["port"])
        edge_json_list.append(
            {
                "source_port": edge.source_port,
                "target_port": edge.target_port,
                "points": [{"x": round(px, 1), "y": round(py, 1)} for px, py in points],
            }
        )

    # Build JSON data
    json_data = _build_json(graph, y_offset, port_positions, edge_json_list, icons)
    return img, json_data


# ── Coordinate helpers ──────────────────────────────────────────────────────


def _to_screen(x: float, y: float, y_offset: float = 0) -> Tuple[float, float]:
    """Convert logical coordinates to screen coordinates."""
    return x * SCALE + PADDING, (y + y_offset) * SCALE + PADDING


def _compute_y_offset(graph: "Graph") -> float:
    """Compute Y offset to shift everything so negative coords become positive."""
    all_y = [n.y for n in graph.nodes]
    for edge in graph.edges:
        for _, by in edge.bend_points:
            all_y.append(by)
        # Detour-rewritten edges may have y-coords beyond the original bends.
        for _, py in edge.full_route:
            all_y.append(py)
    min_y = min(all_y, default=0)
    return max(0, -min_y + 20)


def _compute_canvas_size(graph: "Graph", y_offset: float) -> Tuple[int, int]:
    """Compute canvas pixel dimensions."""
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

    w = int(max_x * SCALE + 2 * PADDING)
    h = int((max_y + y_offset + 20) * SCALE + 2 * PADDING)
    return w, h


# ── Font and icon loading ──────────────────────────────────────────────────


def _load_fonts() -> Dict[str, Any]:
    """Load fonts with fallback. Returns dict with 'header', 'port', 'reaction' keys.

    The previous list only covered macOS (Helvetica.ttc) and Windows
    (arial.ttf). On Linux both miss, and PIL silently falls back to a
    built-in *bitmap* font that ignores the requested size, which renders
    the diagram with unreadably small text. We probe the standard Debian /
    Ubuntu locations next.
    """
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "arial.ttf",  # Windows
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",  # Fedora/RHEL
        "/usr/share/fonts/TTF/DejaVuSans.ttf",  # Arch
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in font_paths:
        try:
            return {
                "header": ImageFont.truetype(path, HEADER_FONT_SIZE),
                "port": ImageFont.truetype(path, PORT_FONT_SIZE),
                "reaction": ImageFont.truetype(path, REACTION_FONT_SIZE),
            }
        except (OSError, IOError):
            continue
    default = ImageFont.load_default()
    return {"header": default, "port": default, "reaction": default}


def _load_icon(name: str) -> Optional[Image.Image]:
    """Load and resize a PNG icon."""
    path = ASSETS_DIR / f"{name}.png"
    if not path.exists():
        return None
    try:
        icon = Image.open(path).convert("RGBA")
        return icon.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    except Exception:
        return None


# ── Port position computation ──────────────────────────────────────────────


def _build_port_positions(graph: "Graph", y_offset: float, icons: dict) -> Dict[str, Tuple[float, float]]:
    """Build mapping from port ID to screen position (connection point)."""
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
                if port.is_input:
                    px = cx - ICON_SIZE / 2 + conn_inset
                else:
                    px = cx + ICON_SIZE / 2 - conn_inset
            else:
                if port.is_input:
                    px = nx  # left edge of node
                else:
                    px = nx + nw  # right edge of node

            positions[port.id] = (px, py)

    return positions


# ── Node drawing ────────────────────────────────────────────────────────────


def _draw_node(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    node: "Node",
    y_offset: float,
    fonts: dict,
    icons: dict,
) -> None:
    """Draw a node: either icon or rounded rectangle with reactions/ports."""
    icon_config = ICON_NODES.get(node.node_type)
    icon = icons.get(node.node_type)

    if icon_config is not None and icon is not None:
        _draw_icon_node(img, draw, node, y_offset, icon, fonts)
    else:
        _draw_rect_node(img, draw, node, y_offset, fonts)


def _draw_icon_node(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    node: "Node",
    y_offset: float,
    icon: Image.Image,
    fonts: dict,
) -> None:
    """Draw a node as an icon (e.g., Timer)."""
    nx, ny = _to_screen(node.x, node.y, y_offset)
    nw = node.width * SCALE

    # Center icon on first port Y
    port_y = node.ports[0].y * SCALE if node.ports else node.height * SCALE / 2
    ix = int(nx + nw / 2 - ICON_SIZE / 2)
    iy = int(ny + port_y - ICON_SIZE / 2)
    img.paste(icon, (ix, iy), icon)

    # Timer label
    if node.node_type == "Timer" and node.init_args:
        label = _get_timer_label(node.init_args)
        if label:
            font = fonts["port"]
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            tx = nx + nw / 2 - tw / 2
            ty = iy + ICON_SIZE + 4 * SCALE
            draw.text((tx, ty), label, fill=COLORS["header_text"], font=font)


def _get_timer_label(init_args: Any) -> Optional[str]:
    """Extract Timer interval and offset from init args."""
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


def _draw_rect_node(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    node: "Node",
    y_offset: float,
    fonts: dict,
) -> None:
    """Draw a rectangular node with header, separator, reactions, and ports."""
    nx, ny = _to_screen(node.x, node.y, y_offset)
    nw = node.width * SCALE
    nh = node.height * SCALE
    header_h = node.header_height * SCALE

    # ── Rounded rectangle (full node) ──
    draw.rounded_rectangle(
        [nx, ny, nx + nw, ny + nh],
        radius=CORNER_RADIUS,
        fill=COLORS["node_fill"],
        outline=COLORS["node_border"],
        width=NODE_BORDER_WIDTH,
    )

    # ── Header background ──
    # Draw a filled rectangle for the header area, clipped by the rounded top
    # We draw a slightly smaller rect that doesn't exceed the corner radius
    hx1 = nx + NODE_BORDER_WIDTH
    hy1 = ny + NODE_BORDER_WIDTH
    hx2 = nx + nw - NODE_BORDER_WIDTH
    hy2 = ny + header_h
    # Use rounded_rectangle for the header to match the top corners
    draw.rounded_rectangle(
        [hx1, hy1, hx2, hy2],
        radius=max(CORNER_RADIUS - NODE_BORDER_WIDTH, 0),
        fill=COLORS["node_header_fill"],
    )
    # Fill the bottom part of header that shouldn't be rounded
    bottom_fill_y = ny + CORNER_RADIUS
    if bottom_fill_y < hy2:
        draw.rectangle(
            [hx1, bottom_fill_y, hx2, hy2],
            fill=COLORS["node_header_fill"],
        )

    # ── Separator line ──
    sep_y = ny + header_h
    draw.line(
        [(nx + NODE_BORDER_WIDTH, sep_y), (nx + nw - NODE_BORDER_WIDTH, sep_y)],
        fill=COLORS["separator"],
        width=max(SCALE, 1),
    )

    # ── Header text (centered) ──
    header_font = fonts["header"]
    bbox = draw.textbbox((0, 0), node.name, font=header_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = nx + nw / 2 - tw / 2
    ty = ny + header_h / 2 - th / 2 - 2 * SCALE
    draw.text((tx, ty), node.name, fill=COLORS["header_text"], font=header_font)

    # ── Ports ──
    input_ports = [p for p in node.ports if p.is_input]
    output_ports = [p for p in node.ports if not p.is_input]

    for port in input_ports:
        _draw_port(draw, port, nx, ny, nw, is_input=True, font=fonts["port"])
    for port in output_ports:
        _draw_port(draw, port, nx, ny, nw, is_input=False, font=fonts["port"])

    # ── Reactions (chevrons) — centered between port label zones ──
    # Compute the center zone boundaries
    left_zone_end = nx + NODE_PAD_H * SCALE + _max_port_label_width(node, True) + PORT_TEXT_PAD
    right_zone_start = nx + nw - NODE_PAD_H * SCALE - _max_port_label_width(node, False) - PORT_TEXT_PAD
    if not input_ports:
        left_zone_end = nx + NODE_PAD_H * SCALE
    if not output_ports:
        right_zone_start = nx + nw - NODE_PAD_H * SCALE

    reaction_screen_info = []
    for reaction in node.reactions:
        info = _draw_reaction_in_zone(draw, reaction, ny, left_zone_end, right_zone_start, fonts["reaction"])
        reaction_screen_info.append((reaction, info))

    # ── Internal connections ──
    _draw_internal_connections(draw, node, nx, ny, nw, reaction_screen_info)


# ── Port drawing ────────────────────────────────────────────────────────────


def _draw_port(
    draw: ImageDraw.ImageDraw,
    port: "Port",
    node_x: float,
    node_y: float,
    node_w: float,
    is_input: bool,
    font: Any,
) -> None:
    """Draw a port triangle and label on the node boundary."""
    py = node_y + port.y * SCALE
    size = PORT_TRIANGLE_SIZE

    if is_input:
        # Triangle on left edge pointing right (into node)
        px = node_x
        triangle = [
            (px - size * 0.3, py - size),
            (px - size * 0.3, py + size),
            (px + size * 0.7, py),
        ]
        # Label to the right of the triangle, inside the node
        text_x = px + PORT_TEXT_PAD
        text_anchor = "lm"
    else:
        # Triangle on right edge pointing right (out of node)
        px = node_x + node_w
        triangle = [
            (px - size * 0.7, py - size),
            (px - size * 0.7, py + size),
            (px + size * 0.3, py),
        ]
        # Label to the left of the triangle, inside the node
        text_x = px - PORT_TEXT_PAD
        text_anchor = "rm"

    draw.polygon(triangle, fill=COLORS["port_fill"])
    draw.text(
        (text_x, py),
        port.short_name,
        fill=COLORS["port_text"],
        font=font,
        anchor=text_anchor,
    )


# ── Reaction drawing ───────────────────────────────────────────────────────


def _draw_reaction_in_zone(
    draw: ImageDraw.ImageDraw,
    reaction: "Reaction",
    node_y: float,
    zone_left: float,
    zone_right: float,
    font: Any,
) -> Tuple[float, float, float, float]:
    """Draw a reaction chevron centered in the zone between port labels.

    Returns (rx, ry, rw, rh) in screen coordinates for internal edge routing.
    """
    bbox = draw.textbbox((0, 0), reaction.name, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pointiness = REACTION_POINTINESS * SCALE
    rh = REACTION_CHEVRON_HEIGHT * SCALE
    rw = max(text_w + 2 * pointiness + 12 * SCALE, REACTION_MIN_WIDTH * SCALE)

    # Center in the available zone between port labels
    zone_center = (zone_left + zone_right) / 2
    rx = zone_center - rw / 2
    ry = node_y + reaction.y * SCALE - rh / 2

    # Draw chevron polygon (6 points)
    points = [
        (rx + pointiness, ry),  # top-left
        (rx + rw - pointiness, ry),  # top-right
        (rx + rw, ry + rh / 2),  # right point
        (rx + rw - pointiness, ry + rh),  # bottom-right
        (rx + pointiness, ry + rh),  # bottom-left
        (rx, ry + rh / 2),  # left point
    ]
    draw.polygon(points, fill=COLORS["reaction_fill"], outline=COLORS["reaction_border"])

    # Draw reaction name centered in the chevron
    tx = rx + rw / 2 - text_w / 2
    ty = ry + rh / 2 - text_h / 2
    draw.text((tx, ty), reaction.name, fill=COLORS["reaction_text"], font=font)

    return (rx, ry, rw, rh)


# ── Internal connection drawing ─────────────────────────────────────────────


def _draw_internal_connections(
    draw: ImageDraw.ImageDraw,
    node: "Node",
    node_x: float,
    node_y: float,
    node_w: float,
    reaction_screen_info: "List[Tuple[Any, Tuple[float, float, float, float]]]",
) -> None:
    """Draw thin lines from input ports to reactions and reactions to output ports."""
    port_screen_y = {}
    for port in node.ports:
        port_screen_y[port.id] = node_y + port.y * SCALE

    color = COLORS["internal_edge"]
    line_w = INTERNAL_EDGE_WIDTH

    for reaction, (rx, ry, rw, rh) in reaction_screen_info:
        react_left_x = rx  # left point of chevron
        react_left_y = ry + rh / 2
        react_right_x = rx + rw  # right point of chevron
        react_right_y = ry + rh / 2

        # Input ports → reaction (connect from port label end to chevron left)
        for port_id in reaction.trigger_ports:
            if port_id in port_screen_y:
                py = port_screen_y[port_id]
                # Start from after the port label
                start_x = node_x + PORT_TEXT_PAD + _port_label_width(node, port_id) + 4 * SCALE
                draw.line(
                    [(start_x, py), (react_left_x, react_left_y)],
                    fill=color,
                    width=line_w,
                )

        # Reaction → output ports (connect from chevron right to before port label)
        for port_id in reaction.effect_ports:
            if port_id in port_screen_y:
                py = port_screen_y[port_id]
                end_x = node_x + node_w - PORT_TEXT_PAD - _port_label_width(node, port_id) - 4 * SCALE
                draw.line(
                    [(react_right_x, react_right_y), (end_x, py)],
                    fill=color,
                    width=line_w,
                )


def _max_port_label_width(node: "Node", is_input: bool) -> float:
    """Get the max label width (screen pixels) for ports on one side."""
    ports = [p for p in node.ports if p.is_input == is_input]
    if not ports:
        return 0
    max_len = max(len(p.short_name) for p in ports)
    return max_len * CHAR_WIDTH * SCALE


def _port_label_width(node: "Node", port_id: str) -> float:
    """Get the label width (screen pixels) for a specific port."""
    for p in node.ports:
        if p.id == port_id:
            return len(p.short_name) * CHAR_WIDTH * SCALE
    return 0


# ── Edge drawing ────────────────────────────────────────────────────────────


def _build_orthogonal_route(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    bends: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """Build a strictly orthogonal route from source to target through ELK bend points.

    Guarantees:
    - Every segment is strictly horizontal or vertical.
    - First segment leaves the source port horizontally.
    - Last segment enters the target port horizontally.
    - Vertical transitions happen at ELK bend x-coordinates (in the gaps between nodes).

    For N intermediate bend points the route is:
        source -H-> bend[0].x -V-> bend[0].y -H-> bend[1].x -V-> ... -H-> last_bend.x -V-> ty -H-> target
    The final vertical goes directly to target y (not the last bend y),
    ensuring horizontal entry into the target port.
    """
    if not bends:
        # No bend points — direct horizontal or single-turn route
        if abs(sy - ty) <= 1:
            return [(sx, sy), (tx, ty)]
        mx = (sx + tx) / 2
        return [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]

    points: List[Tuple[float, float]] = [(sx, sy)]
    cur_y = sy

    for i, (bx, by) in enumerate(bends):
        is_last = i == len(bends) - 1

        # Horizontal to this bend's x-coordinate
        points.append((bx, cur_y))

        if is_last:
            # Final bend: transition to target y (not bend y)
            # so the edge enters the target port horizontally
            cur_y = ty
        else:
            # Intermediate bend: use bend y as the routing channel
            cur_y = by

        points.append((bx, cur_y))

    # Final horizontal into target
    points.append((tx, cur_y))

    return _optimize_route(points)


def _optimize_route(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Remove redundant points and collapse near-zero-length segments.

    - Removes consecutive duplicate points.
    - Collapses vertical segments shorter than a threshold into a horizontal line.
    - Merges collinear consecutive segments (same direction).
    """
    if len(points) < 2:
        return points

    EPSILON = 2.0  # pixel threshold for "same coordinate"

    # 1. Snap near-equal y-coordinates in consecutive points
    #    If two consecutive points differ by < EPSILON in y, unify them.
    snapped: List[Tuple[float, float]] = [points[0]]
    for i in range(1, len(points)):
        px, py = snapped[-1]
        nx, ny = points[i]
        if abs(ny - py) < EPSILON:
            ny = py  # snap to same y
        if abs(nx - px) < EPSILON:
            nx = px  # snap to same x
        snapped.append((nx, ny))

    # 2. Remove consecutive duplicates
    deduped: List[Tuple[float, float]] = [snapped[0]]
    for i in range(1, len(snapped)):
        px, py = deduped[-1]
        nx, ny = snapped[i]
        if abs(nx - px) > EPSILON or abs(ny - py) > EPSILON:
            deduped.append((nx, ny))

    # 3. Merge collinear segments (3 points on the same H or V line)
    if len(deduped) < 3:
        return deduped
    merged: List[Tuple[float, float]] = [deduped[0]]
    for i in range(1, len(deduped) - 1):
        ax, ay = merged[-1]
        bx, by = deduped[i]
        cx, cy = deduped[i + 1]
        # If all three are on the same horizontal or vertical line, skip middle
        same_h = abs(ay - by) < EPSILON and abs(by - cy) < EPSILON
        same_v = abs(ax - bx) < EPSILON and abs(bx - cx) < EPSILON
        if not (same_h or same_v):
            merged.append((bx, by))
    merged.append(deduped[-1])

    return merged


def _draw_edge(
    draw: ImageDraw.ImageDraw,
    edge: "Edge",
    port_positions: Dict[str, Tuple[float, float]],
    y_offset: float,
    font: Any,
) -> List[Tuple[float, float]]:
    """Draw an orthogonal edge with arrowhead. Returns the point list."""
    src = port_positions.get(edge.source_port)
    tgt = port_positions.get(edge.target_port)
    if not src or not tgt:
        return []
    sx, sy = src
    tx, ty = tgt

    if edge.full_route:
        # A post-processor (e.g. _avoid_node_body_crossings) already produced
        # the orthogonal route in logical coords; use it verbatim instead of
        # reconstructing from bends (which would put us back in the bug).
        points = [_to_screen(px, py, y_offset) for px, py in edge.full_route]
        points = _optimize_route(points)
    else:
        scaled_bends = [_to_screen(bx, by, y_offset) for bx, by in edge.bend_points]
        points = _build_orthogonal_route(sx, sy, tx, ty, scaled_bends)

    # Draw edge as rounded orthogonal path. Physical connections render dashed.
    if len(points) >= 2:
        _draw_rounded_polyline(
            draw,
            points,
            COLORS["edge"],
            EDGE_WIDTH,
            radius=6 * SCALE,
            dashed=edge.is_physical,
        )

    # Draw arrowhead at target
    if len(points) >= 2:
        _draw_arrowhead(draw, points[-2], points[-1])

    # Draw delay label
    label = _format_delay_label(edge.delay)
    if label and len(points) >= 2:
        lx, ly, horizontal = _longest_segment_midpoint(points)
        if horizontal:
            draw.text((lx, ly - 4 * SCALE), label, fill=COLORS["edge_label"], font=font, anchor="ms")
        else:
            draw.text((lx + 4 * SCALE, ly), label, fill=COLORS["edge_label"], font=font, anchor="lm")

    return points


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


def _draw_rounded_polyline(
    draw: ImageDraw.ImageDraw,
    points: List[Tuple[float, float]],
    fill: str,
    width: int,
    radius: float = 18,
    dashed: bool = False,
) -> None:
    """Draw a polyline with rounded corners at bend points using arcs.

    When ``dashed`` is True, every segment (including the bend arcs) is drawn
    as a dash pattern instead of a continuous line.
    """
    if len(points) < 2:
        return
    if len(points) == 2:
        _draw_segment(draw, points[0], points[1], fill, width, dashed)
        return

    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]

        if i > 0:
            # Shorten start to make room for the previous arc
            px, py = points[i - 1]
            r = min(
                radius,
                abs(x2 - x1) / 2 if abs(x2 - x1) > 0 else radius,
                abs(y2 - y1) / 2 if abs(y2 - y1) > 0 else radius,
                abs(x1 - px) / 2 if abs(x1 - px) > 0 else radius,
                abs(y1 - py) / 2 if abs(y1 - py) > 0 else radius,
            )
            if abs(x2 - x1) > 0:  # horizontal segment
                x1 = x1 + r * (1 if x2 > x1 else -1)
            else:  # vertical segment
                y1 = y1 + r * (1 if y2 > y1 else -1)

        if i < len(points) - 2:
            # Shorten end to make room for the next arc
            nx, ny = points[i + 1]
            nnx, nny = points[i + 2]
            r = min(
                radius,
                abs(x2 - x1) / 2 if abs(x2 - x1) > 0 else radius,
                abs(y2 - y1) / 2 if abs(y2 - y1) > 0 else radius,
                abs(nnx - nx) / 2 if abs(nnx - nx) > 0 else radius,
                abs(nny - ny) / 2 if abs(nny - ny) > 0 else radius,
            )
            if abs(x2 - x1) > 0:  # horizontal segment
                x2 = x2 - r * (1 if x2 > x1 else -1)
            else:  # vertical segment
                y2 = y2 - r * (1 if y2 > y1 else -1)

        _draw_segment(draw, (x1, y1), (x2, y2), fill, width, dashed)

        # Draw arc at the bend
        if i < len(points) - 2:
            _draw_bend_arc(draw, points[i], points[i + 1], points[i + 2], fill, width, radius, dashed=dashed)


# Length of each dash and gap (in screen units) for physical (dashed) edges.
DASH_LEN = 6 * SCALE
DASH_GAP = 4 * SCALE


def _draw_segment(
    draw: ImageDraw.ImageDraw,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    fill: str,
    width: int,
    dashed: bool,
) -> None:
    """Draw a straight line segment, optionally as a dash pattern."""
    if not dashed:
        draw.line([p1, p2], fill=fill, width=width)
        return
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return
    ux = dx / length
    uy = dy / length
    period = DASH_LEN + DASH_GAP
    pos = 0.0
    while pos < length:
        end = min(pos + DASH_LEN, length)
        sx = x1 + ux * pos
        sy = y1 + uy * pos
        ex = x1 + ux * end
        ey = y1 + uy * end
        draw.line([(sx, sy), (ex, ey)], fill=fill, width=width)
        pos += period


def _draw_bend_arc(
    draw: ImageDraw.ImageDraw,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    fill: str,
    width: int,
    radius: float,
    dashed: bool = False,
) -> None:
    """Draw a rounded corner arc at point p2 between segments p1-p2 and p2-p3."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3

    # Compute actual radius limited by segment lengths
    seg1_len = max(abs(x2 - x1), abs(y2 - y1))
    seg2_len = max(abs(x3 - x2), abs(y3 - y2))
    r = min(radius, seg1_len / 2, seg2_len / 2)
    if r < 2:
        return

    # Determine the incoming and outgoing directions
    dx_in = 1 if x2 > x1 else (-1 if x2 < x1 else 0)
    dy_in = 1 if y2 > y1 else (-1 if y2 < y1 else 0)
    dx_out = 1 if x3 > x2 else (-1 if x3 < x2 else 0)
    dy_out = 1 if y3 > y2 else (-1 if y3 < y2 else 0)

    # Arc start and end points
    start_x = x2 - dx_in * r
    start_y = y2 - dy_in * r
    end_x = x2 + dx_out * r
    end_y = y2 + dy_out * r

    # Approximate arc with line segments
    n_segments = 6
    arc_points = []
    for j in range(n_segments + 1):
        t = j / n_segments
        # Interpolate between start and end along arc
        ax = start_x + (end_x - start_x) * t
        ay = start_y + (end_y - start_y) * t
        # Push outward to approximate curve
        mid_t = 1 - abs(2 * t - 1)  # peaks at 0.5
        bulge = r * 0.41 * mid_t  # ~= r*(1-cos(45)) ≈ 0.29*r, but 0.41 gives rounder
        # Direction of bulge is toward the corner point
        bx = x2 - (start_x + end_x) / 2
        by = y2 - (start_y + end_y) / 2
        bl = (bx * bx + by * by) ** 0.5
        if bl > 0:
            ax += bx / bl * bulge
            ay += by / bl * bulge
        arc_points.append((ax, ay))

    if len(arc_points) >= 2:
        if dashed:
            for k in range(len(arc_points) - 1):
                _draw_segment(draw, arc_points[k], arc_points[k + 1], fill, width, dashed=True)
        else:
            draw.line(arc_points, fill=fill, width=width)


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    from_pt: Tuple[float, float],
    to_pt: Tuple[float, float],
) -> None:
    """Draw a filled arrowhead at to_pt pointing in the direction from from_pt to to_pt."""
    fx, fy = from_pt
    tx, ty = to_pt

    # Determine direction
    dx = tx - fx
    dy = ty - fy
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1:
        return

    # Normalize
    ux, uy = dx / length, dy / length
    # Perpendicular
    px, py = -uy, ux

    al = ARROWHEAD_LENGTH
    aw = ARROWHEAD_WIDTH / 2

    # Arrow tip at to_pt, base behind
    arrow = [
        (tx, ty),
        (tx - ux * al + px * aw, ty - uy * al + py * aw),
        (tx - ux * al - px * aw, ty - uy * al - py * aw),
    ]
    draw.polygon(arrow, fill=COLORS["arrowhead"])


# ── JSON data builder ──────────────────────────────────────────────────────


def _build_json(
    graph: "Graph",
    y_offset: float,
    port_positions: Dict[str, Tuple[float, float]],
    edge_json_list: List[dict],
    icons: dict,
) -> dict:
    """Build JSON-serializable dict with positions of all diagram elements."""
    nodes_json = []
    for node in graph.nodes:
        sx, sy = _to_screen(node.x, node.y, y_offset)
        sw = node.width * SCALE
        sh = node.height * SCALE

        ports_json = []
        for port in node.ports:
            pp = port_positions.get(port.id, (0, 0))
            ports_json.append(
                {
                    "id": port.id,
                    "name": port.short_name,
                    "is_input": port.is_input,
                    "x": round(pp[0], 1),
                    "y": round(pp[1], 1),
                }
            )

        reactions_json = []
        for reaction in node.reactions:
            # Approximate reaction screen position (centered in node)
            rh = REACTION_CHEVRON_HEIGHT * SCALE
            ry = sy + reaction.y * SCALE - rh / 2
            # Width approximation
            text_w = len(reaction.name) * CHAR_WIDTH * SCALE
            pointiness = REACTION_POINTINESS * SCALE
            rw = max(text_w + 2 * pointiness + 12 * SCALE, REACTION_MIN_WIDTH * SCALE)
            rx = sx + sw / 2 - rw / 2

            reactions_json.append(
                {
                    "name": reaction.name,
                    "x": round(rx, 1),
                    "y": round(ry, 1),
                    "width": round(rw, 1),
                    "height": round(rh, 1),
                    "trigger_ports": reaction.trigger_ports,
                    "effect_ports": reaction.effect_ports,
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
