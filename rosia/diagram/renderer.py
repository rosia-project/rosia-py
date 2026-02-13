"""Core rendering logic for drawing graphs to PIL images."""

from pathlib import Path
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from rosia.time import Time
from rosia.diagram.constants import (
    SCALE,
    PADDING,
    ICON_SIZE,
    NODE_BORDER_WIDTH,
    PORT_TRIANGLE_SIZE,
    EDGE_WIDTH,
    FONT_SIZE,
    PORT_FONT_SIZE,
    PORT_TEXT_PADDING,
    COLORS,
    ICON_NODES,
)

if TYPE_CHECKING:
    from rosia.diagram.diagram import Graph, Node, Port, Edge

# Assets
ASSETS_DIR = Path(__file__).parent / "assets"


def render_graph(graph: "Graph") -> Image.Image:
    """Render a graph to a PIL Image."""
    # Calculate canvas size
    max_x = max((n.x + n.width for n in graph.nodes), default=0)
    max_y = max((n.y + n.height for n in graph.nodes), default=0)
    width = int(max_x * SCALE + 2 * PADDING)
    height = int(max_y * SCALE + 2 * PADDING)

    # Create image and drawing context
    img = Image.new("RGB", (width, height), COLORS["background"])
    draw = ImageDraw.Draw(img)
    font, port_font = _load_fonts()

    # Load icons
    icons = {name: _load_icon(name.lower()) for name in ICON_NODES.keys()}

    # Build port position map for edges
    port_positions = _build_port_positions(graph, icons)

    # Draw nodes and edges
    for node in graph.nodes:
        _draw_node(img, draw, node, font, port_font, icons)

    for edge in graph.edges:
        _draw_edge(draw, edge, port_positions)

    return img


def _load_fonts():
    """Load fonts with fallback."""
    for path in ["/System/Library/Fonts/Helvetica.ttc", "arial.ttf"]:
        try:
            return (
                ImageFont.truetype(path, FONT_SIZE),
                ImageFont.truetype(path, PORT_FONT_SIZE),
            )
        except (OSError, IOError):
            continue
    default = ImageFont.load_default()
    return default, default


def _load_icon(name: str) -> Optional[Image.Image]:
    """Load and resize a PNG icon."""
    path = ASSETS_DIR / f"{name}.png"
    if not path.exists():
        return None
    try:
        img = Image.open(path).convert("RGBA")
        return img.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    except Exception:
        return None


def _scale_pos(x: float, y: float) -> Tuple[float, float]:
    """Apply scale and padding to coordinates."""
    return x * SCALE + PADDING, y * SCALE + PADDING


def _build_port_positions(
    graph: "Graph", icons: dict
) -> Dict[str, Tuple[float, float]]:
    """Build mapping from port ID to screen position."""
    positions = {}

    for node in graph.nodes:
        nx, ny = _scale_pos(node.x, node.y)
        nw, _ = node.width * SCALE, node.height * SCALE
        icon_config = ICON_NODES.get(node.node_type)
        is_icon = icon_config is not None and icons.get(node.node_type) is not None

        for port in node.ports:
            if is_icon and icon_config is not None:
                # Icon center is at port y (from ELK), horizontally centered
                conn_inset = icon_config.get("connection_inset", 0) * SCALE
                cy = ny + port.y * SCALE

                # Connection point inset from icon edge (horizontal)
                cx = nx + nw / 2
                if port.is_input:
                    px = cx - ICON_SIZE / 2 + conn_inset
                else:
                    px = cx + ICON_SIZE / 2 - conn_inset
                py = cy
            else:
                py = ny + port.y * SCALE
                px = nx if port.is_input else nx + nw + PORT_TRIANGLE_SIZE

            positions[port.id] = (px, py)

    return positions


def _draw_node(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    node: "Node",
    font,
    port_font,
    icons: dict,
) -> None:
    """Draw a node (either as icon or rectangle with ports)."""
    x, y = _scale_pos(node.x, node.y)
    w, h = node.width * SCALE, node.height * SCALE

    icon_config = ICON_NODES.get(node.node_type)
    icon = icons.get(node.node_type)
    if icon_config is not None and icon is not None:
        # Get port y-position (use first port's y as icon center)
        port_y = node.ports[0].y * SCALE if node.ports else h / 2
        _draw_icon_node(img, draw, x, y, w, icon, node, port_font, port_y)
    else:
        _draw_rect_node(draw, x, y, w, h, node, font, port_font)


def _draw_icon_node(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    icon: Image.Image,
    node: "Node",
    font,
    port_y: float,
) -> None:
    """Draw a node as an icon centered on port y-position."""
    # Center icon horizontally, and vertically on the port y
    ix = int(x + w / 2 - ICON_SIZE / 2)
    iy = int(y + port_y - ICON_SIZE / 2)
    img.paste(icon, (ix, iy), icon)

    if node.node_type == "Timer" and node.init_args:
        label = _get_timer_label(node.init_args)
        if label:
            bbox = draw.textbbox((0, 0), label, font=font)
            tx = x + w / 2 - (bbox[2] - bbox[0]) / 2
            ty = iy + ICON_SIZE + 5 * SCALE
            draw.text((tx, ty), label, fill=COLORS["text"], font=font)


def _get_timer_label(init_args) -> Optional[str]:
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

    return f"({interval},{offset})"


def _draw_rect_node(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    h: float,
    node: "Node",
    font,
    port_font,
) -> None:
    """Draw a rectangular node with ports."""
    draw.rectangle(
        [x, y, x + w, y + h],
        fill=COLORS["node_fill"],
        outline=COLORS["node_border"],
        width=NODE_BORDER_WIDTH,
    )

    bbox = draw.textbbox((0, 0), node.name, font=font)
    tx = x + w / 2 - (bbox[2] - bbox[0]) / 2
    draw.text((tx, y + 10 * SCALE), node.name, fill=COLORS["text"], font=font)

    for port in node.ports:
        _draw_port(draw, port, x, y, w, port_font)


def _draw_port(
    draw: ImageDraw.ImageDraw,
    port: "Port",
    node_x: float,
    node_y: float,
    node_w: float,
    font,
) -> None:
    """Draw a port triangle and label."""
    py = node_y + port.y * SCALE
    size = PORT_TRIANGLE_SIZE

    if port.is_input:
        px = node_x
        triangle = [(px, py - size), (px, py + size), (px + size, py)]
        text_pos = (px + PORT_TEXT_PADDING, py)
        anchor = "lm"
    else:
        px = node_x + node_w
        triangle = [(px, py - size), (px, py + size), (px + size, py)]
        text_pos = (px - PORT_TEXT_PADDING, py)
        anchor = "rm"

    draw.polygon(triangle, fill=COLORS["port"])
    draw.text(text_pos, port.short_name, fill=COLORS["text"], font=font, anchor=anchor)


def _draw_edge(
    draw: ImageDraw.ImageDraw,
    edge: "Edge",
    port_positions: Dict[str, Tuple[float, float]],
) -> None:
    """Draw an orthogonal edge between ports."""
    src = port_positions.get(edge.source_port)
    tgt = port_positions.get(edge.target_port)

    if not src or not tgt:
        return

    sx, sy = src
    tx, ty = tgt
    mx = (sx + tx) / 2

    points = [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]
    draw.line(points, fill=COLORS["edge"], width=EDGE_WIDTH)
