from __future__ import annotations

from typing import Iterable

from tool_server.diagrams.diagram_sketch_svg import DiagramEdge, DiagramNode, render_flow_diagram_svg
from tool_server.vector_renderer import VectorArtifact


def render_d2_flow_svg(
    nodes: Iterable[DiagramNode | dict | str],
    edges: Iterable[DiagramEdge | dict | tuple[str, str]],
    *,
    title: str = "Flow diagram",
    width: int = 720,
    height: int = 320,
) -> VectorArtifact:
    artifact = render_flow_diagram_svg(nodes, edges, title=title, width=width, height=height)
    metadata = dict(artifact.metadata or {})
    metadata["adapter"] = "d2-compatible"
    return VectorArtifact(
        kind=artifact.kind,
        body=artifact.body,
        width=artifact.width,
        height=artifact.height,
        metadata=metadata,
    )
