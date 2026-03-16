"""Graph building and layout for rosia node visualization."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from pyelk import ELK  # pyright: ignore[reportMissingImports]

from rosia.diagram.constants import (
    CHAR_WIDTH,
    PORT_ROW_HEIGHT,
    NODE_PADDING,
    PORT_GAP,
    MIN_NODE_SIZE,
    ICON_NODES,
)
from rosia.diagram.renderer import render_graph
import rosia

if TYPE_CHECKING:
    from rosia.coordinate.Coordinator import NodeRuntimeInfo


@dataclass
class Port:
    id: str
    short_name: str
    is_input: bool
    y: float = 0  # Relative Y position (set by ELK)


@dataclass
class Node:
    id: str
    name: str
    node_type: str
    ports: List[Port]
    init_args: Optional[object] = None
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


@dataclass
class Edge:
    source_port: str
    target_port: str
    bend_points: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class Graph:
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)


def diagram(
    node_infos: "Dict[str, NodeRuntimeInfo]",
    save_to: Optional[str] = None,
    rerun: bool = True,
) -> None:
    """Main entry point: build graph, layout with ELK, and render.

    Args:
        node_infos: Node runtime info from the coordinator.
        save_to: If provided, save the diagram image to this file path.
        rerun: If True, send the diagram to the rerun viewer.
    """
    if not node_infos:
        return

    graph = build_graph(node_infos)
    layout_graph(graph)

    image = render_graph(graph)

    if save_to:
        image.save(save_to)

    if rerun:
        rosia.rerun_manager.send_blueprint()
        rosia.rerun_manager.render_diagram(image)


def build_graph(node_infos: "Dict[str, NodeRuntimeInfo]") -> Graph:
    """Convert node runtime info to graph representation."""
    graph = Graph()

    for node_name, node_info in node_infos.items():
        runtime = node_info.node
        node_type = runtime.node_cls.__name__.replace("NodeRuntime", "")

        # Get init args from class annotations
        init_args = None
        if hasattr(runtime.node_cls, "_rosia_annotations"):
            init_args = runtime.node_cls._rosia_annotations.get("init_args")

        # Build ports
        ports = []
        for port_name in runtime.input_port_connectors:
            short_name = port_name.split(".", 1)[1]
            ports.append(Port(id=port_name, short_name=short_name, is_input=True))

        for port_name in runtime.output_port_connectors:
            short_name = port_name.split(".", 1)[1]
            ports.append(Port(id=port_name, short_name=short_name, is_input=False))

        # Compute node size
        width, height = _compute_node_size(node_name, ports, node_type)

        graph.nodes.append(
            Node(
                id=node_name,
                name=node_name,
                node_type=node_type,
                ports=ports,
                init_args=init_args,
                width=width,
                height=height,
            )
        )

        # Build edges
        for port_name, connector in runtime.output_port_connectors.items():
            for downstream in connector.downstream_ports:
                graph.edges.append(
                    Edge(source_port=port_name, target_port=downstream.name)
                )

    return graph


def _compute_node_size(
    name: str, ports: List[Port], node_type: str
) -> Tuple[float, float]:
    """Compute node dimensions based on name and ports."""
    input_ports = [p for p in ports if p.is_input]
    output_ports = [p for p in ports if not p.is_input]

    max_ports = max(len(input_ports), len(output_ports), 1)
    height = NODE_PADDING[0] + max_ports * PORT_ROW_HEIGHT + NODE_PADDING[1]

    # For icon nodes (like Timer), use configured width or default minimum
    is_icon_node = node_type in ICON_NODES
    if is_icon_node:
        icon_config = ICON_NODES[node_type]
        width = icon_config.get("width", MIN_NODE_SIZE[0])
    else:
        name_width = len(name) * CHAR_WIDTH + 2 * NODE_PADDING[2]
        max_in_len = max((len(p.short_name) for p in input_ports), default=0)
        max_out_len = max((len(p.short_name) for p in output_ports), default=0)
        port_width = (
            (max_in_len + max_out_len) * CHAR_WIDTH + PORT_GAP + 2 * NODE_PADDING[2]
        )
        width = max(name_width, port_width, MIN_NODE_SIZE[0])

    return (
        width,
        max(height, MIN_NODE_SIZE[1]),
    )


def layout_graph(graph: Graph) -> None:
    """Use ELK to compute node and port positions."""
    # Convert to ELK format
    elk_children = []
    for node in graph.nodes:
        elk_ports = [
            {
                "id": p.id,
                "width": 10,
                "height": 10,
                "layoutOptions": {"elk.port.side": "WEST" if p.is_input else "EAST"},
            }
            for p in node.ports
        ]
        elk_children.append(
            {
                "id": node.id,
                "width": node.width,
                "height": node.height,
                "ports": elk_ports,
                "layoutOptions": {"elk.portConstraints": "FIXED_SIDE"},
            }
        )

    elk_edges = [
        {"id": f"e{i}", "sources": [e.source_port], "targets": [e.target_port]}
        for i, e in enumerate(graph.edges)
    ]

    elk_graph = {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": "RIGHT",
            "elk.spacing.nodeNode": "60",
            "elk.layered.spacing.nodeNodeBetweenLayers": "120",
            "elk.edgeRouting": "ORTHOGONAL",
        },
        "children": elk_children,
        "edges": elk_edges,
    }

    # Run ELK layout
    result = ELK().layout(elk_graph)

    # Copy positions back to our graph
    node_map = {n.id: n for n in graph.nodes}
    for elk_node in result.get("children", []):
        node = node_map.get(elk_node["id"])
        if node:
            node.x = elk_node["x"]
            node.y = elk_node["y"]
            port_map = {p.id: p for p in node.ports}
            for elk_port in elk_node.get("ports", []):
                port = port_map.get(elk_port["id"])
                if port:
                    port.y = elk_port.get("y", 0)

    # Extract edge bend points from ELK result
    edge_map = {f"e{i}": e for i, e in enumerate(graph.edges)}
    for elk_edge in result.get("edges", []):
        edge = edge_map.get(elk_edge["id"])
        if edge:
            for section in elk_edge.get("sections", []):
                bend_points = []
                for bp in section.get("bendPoints", []):
                    bend_points.append((bp["x"], bp["y"]))
                edge.bend_points = bend_points
