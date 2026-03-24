"""Shared constants for diagram visualization."""

# ── Layout constants (unscaled, in logical/ELK units) ──────────────────────

CHAR_WIDTH = 5.5  # average character width for size estimation (body text)
CHAR_WIDTH_HEADER = 7.0  # slightly wider for header font

HEADER_HEIGHT = 34.0  # height of node name area
ROW_HEIGHT = 34.0  # vertical spacing per row in body
NODE_BODY_PAD_TOP = 10.0  # padding above first row in body
NODE_BODY_PAD_BOTTOM = 8.0  # padding below last row in body
NODE_PAD_H = 12.0  # horizontal padding inside node

MIN_NODE_WIDTH = 110.0
MIN_NODE_HEIGHT = 70.0

PORT_TRI_SIZE = 7.0  # port triangle size (unscaled)
PORT_LABEL_GAP = 6.0  # gap between port triangle and label text
REACTION_GAP_H = 8.0  # horizontal gap between port labels and reaction
REACTION_POINTINESS = 7.0  # chevron point length
REACTION_CHEVRON_HEIGHT = 24.0  # height of reaction chevron
REACTION_MIN_WIDTH = 60.0  # minimum reaction chevron width

CORNER_RADIUS_UNSCALED = 8.0  # rounded rectangle corner radius

# ── Scaling ─────────────────────────────────────────────────────────────────

SCALE = 3

# ── Drawing constants (pre-scaled for rendering) ───────────────────────────

PADDING = 50 * SCALE
ICON_SIZE = 64 * SCALE
NODE_BORDER_WIDTH = 2 * SCALE
EDGE_WIDTH = 2 * SCALE
INTERNAL_EDGE_WIDTH = 1 * SCALE
HEADER_FONT_SIZE = 14 * SCALE
PORT_FONT_SIZE = 11 * SCALE
REACTION_FONT_SIZE = 11 * SCALE
PORT_TRIANGLE_SIZE = PORT_TRI_SIZE * SCALE
CORNER_RADIUS = CORNER_RADIUS_UNSCALED * SCALE
ARROWHEAD_LENGTH = 10 * SCALE
ARROWHEAD_WIDTH = 7 * SCALE
PORT_TEXT_PAD = 8 * SCALE  # padding from port triangle to label (screen)

# ── Colors (Lingua Franca inspired) ────────────────────────────────────────

COLORS = {
    "background": "#FFFFFF",
    "node_fill": "#F0F0F0",
    "node_border": "#888888",
    "node_header_fill": "#E4E4E4",
    "separator": "#C0C0C0",
    "header_text": "#2A2A2A",
    "port_text": "#3A3A3A",
    "port_fill": "#2A2A2A",
    "reaction_fill": "#6E6E6E",
    "reaction_border": "#555555",
    "reaction_text": "#FFFFFF",
    "edge": "#505050",
    "arrowhead": "#505050",
    "internal_edge": "#B0B0B0",
}

# ── Icon node configuration (unscaled values) ──────────────────────────────

ICON_NODES = {
    "Timer": {
        "connection_inset": 10,
        "width": 60.0,
    },
}
