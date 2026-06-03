from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tool_server.vector_renderer import VectorArtifact, stable_json, svg_document, xml_attr, xml_text


@dataclass(frozen=True)
class DiagramNode:
    node_id: str
    label: str | None = None


@dataclass(frozen=True)
class DiagramEdge:
    source: str
    target: str
    label: str | None = None


def render_flow_diagram_svg(
    nodes: Iterable[DiagramNode | dict | str],
    edges: Iterable[DiagramEdge | dict | tuple[str, str]],
    *,
    title: str = "Flow diagram",
    width: int = 720,
    height: int = 320,
) -> VectorArtifact:
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(edges)
    if width < 320 or height < 180:
        raise ValueError("diagram canvas is too small")
    node_ids = {node.node_id for node in normalized_nodes}
    for edge in normalized_edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError(f"edge references unknown node: {edge.source}->{edge.target}")

    x_start = 48
    x_end = width - 48
    y = height // 2
    node_width = 136
    node_height = 48
    step = 0 if len(normalized_nodes) == 1 else (x_end - x_start) / (len(normalized_nodes) - 1)
    positions = {
        node.node_id: (
            int(x_start + index * step - node_width / 2),
            y - node_height // 2,
        )
        for index, node in enumerate(normalized_nodes)
    }

    children = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="32" font-size="18" font-family="Arial" '
        f'font-weight="700" fill="#111827">{xml_text(title)}</text>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#4b5563"/></marker></defs>',
    ]
    for edge in normalized_edges:
        source_x, source_y = positions[edge.source]
        target_x, target_y = positions[edge.target]
        x1 = source_x + node_width
        y1 = source_y + node_height // 2
        x2 = target_x
        y2 = target_y + node_height // 2
        children.append(
            f'<line data-edge="{xml_attr(edge.source)}->{xml_attr(edge.target)}" '
            f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#4b5563" '
            'stroke-width="2" marker-end="url(#arrow)"/>'
        )
        if edge.label:
            children.append(
                f'<text x="{(x1 + x2) // 2}" y="{y1 - 12}" font-size="11" '
                f'font-family="Arial" fill="#374151" text-anchor="middle">{xml_text(edge.label)}</text>'
            )

    for node in normalized_nodes:
        x, node_y = positions[node.node_id]
        children.extend(
            [
                f'<rect data-node="{xml_attr(node.node_id)}" x="{x}" y="{node_y}" '
                f'width="{node_width}" height="{node_height}" rx="6" fill="#eef6fb" '
                'stroke="#255f85" stroke-width="1.5"/>',
                f'<text x="{x + node_width // 2}" y="{node_y + 30}" font-size="13" '
                f'font-family="Arial" fill="#111827" text-anchor="middle">{xml_text(node.label or node.node_id)}</text>',
            ]
        )

    svg = svg_document(
        width=width,
        height=height,
        title=title,
        description="Deterministic local SVG flow diagram",
        children=children,
    )
    return VectorArtifact(
        kind="diagram.flow",
        body=svg,
        width=width,
        height=height,
        metadata={
            "node_count": len(normalized_nodes),
            "edge_count": len(normalized_edges),
            "graph_hash_input": stable_json(
                {
                    "nodes": [node.__dict__ for node in normalized_nodes],
                    "edges": [edge.__dict__ for edge in normalized_edges],
                }
            ),
        },
    )


def _normalize_nodes(nodes: Iterable[DiagramNode | dict | str]) -> tuple[DiagramNode, ...]:
    normalized: list[DiagramNode] = []
    for node in nodes:
        if isinstance(node, DiagramNode):
            item = node
        elif isinstance(node, dict):
            item = DiagramNode(
                node_id=str(node["node_id"]),
                label=str(node["label"]) if node.get("label") is not None else None,
            )
        else:
            item = DiagramNode(node_id=str(node))
        if not item.node_id:
            raise ValueError("diagram node id is required")
        normalized.append(item)
    if not normalized:
        raise ValueError("at least one diagram node is required")
    ids = [node.node_id for node in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("diagram node ids must be unique")
    return tuple(sorted(normalized, key=lambda item: item.node_id))


def _normalize_edges(edges: Iterable[DiagramEdge | dict | tuple[str, str]]) -> tuple[DiagramEdge, ...]:
    normalized: list[DiagramEdge] = []
    for edge in edges:
        if isinstance(edge, DiagramEdge):
            item = edge
        elif isinstance(edge, dict):
            item = DiagramEdge(
                source=str(edge["source"]),
                target=str(edge["target"]),
                label=str(edge["label"]) if edge.get("label") is not None else None,
            )
        else:
            source, target = edge
            item = DiagramEdge(source=str(source), target=str(target))
        normalized.append(item)
    return tuple(sorted(normalized, key=lambda item: (item.source, item.target, item.label or "")))
