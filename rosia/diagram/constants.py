"""Shared constants for visualization."""

# Layout constants (unscaled)
CHAR_WIDTH = 16.0
PORT_ROW_HEIGHT = 48.0
NODE_PADDING = (60.0, 10.0, 30.0)  # top, bottom, horizontal
PORT_GAP = 10.0
MIN_NODE_SIZE = (100.0, 80.0)  # width, height

# Scaling
SCALE = 3

# Drawing constants (pre-scaled)
PADDING = 50 * SCALE
ICON_SIZE = 64 * SCALE
NODE_BORDER_WIDTH = 2 * SCALE
PORT_TRIANGLE_SIZE = 8 * SCALE
EDGE_WIDTH = 2 * SCALE
FONT_SIZE = 18 * SCALE
PORT_FONT_SIZE = 16 * SCALE
PORT_TEXT_PADDING = 15 * SCALE

# Colors
COLORS = {
    "background": "white",
    "node_fill": "white",
    "node_border": "black",
    "text": "black",
    "port": "black",
    "edge": "black",
}

# Icon node configuration (unscaled values)
# - connection_inset: horizontal inset from icon edge for line connection
ICON_NODES = {
    "Timer": {
        "connection_inset": 10,
    },
}
