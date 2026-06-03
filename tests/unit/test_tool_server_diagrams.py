import pytest

from tool_server.diagrams import render_d2_flow_svg, render_flow_diagram_svg


def test_flow_diagram_svg_is_deterministic_for_unsorted_input():
    first = render_flow_diagram_svg(
        nodes=[
            {"node_id": "research", "label": "Research"},
            {"node_id": "intake", "label": "Intake"},
            {"node_id": "slides", "label": "Slides"},
        ],
        edges=[
            {"source": "research", "target": "slides", "label": "evidence"},
            {"source": "intake", "target": "research", "label": "brief"},
        ],
        title="PFOS flow",
    ).as_payload()
    second = render_flow_diagram_svg(
        nodes=[
            {"node_id": "slides", "label": "Slides"},
            {"node_id": "research", "label": "Research"},
            {"node_id": "intake", "label": "Intake"},
        ],
        edges=[
            {"source": "intake", "target": "research", "label": "brief"},
            {"source": "research", "target": "slides", "label": "evidence"},
        ],
        title="PFOS flow",
    ).as_payload()

    assert first["content_hash"] == second["content_hash"]
    assert first["metadata"]["node_count"] == 3
    assert first["metadata"]["edge_count"] == 2
    assert 'data-node="intake"' in first["body"]
    assert 'data-edge="intake->research"' in first["body"]


def test_flow_diagram_rejects_unknown_edge_node():
    with pytest.raises(ValueError, match="unknown node"):
        render_flow_diagram_svg(nodes=["a"], edges=[("a", "missing")])


def test_d2_adapter_preserves_diagram_contract():
    artifact = render_d2_flow_svg(nodes=["a", "b"], edges=[("a", "b")])

    assert artifact.kind == "diagram.flow"
    assert artifact.metadata["adapter"] == "d2-compatible"
    assert artifact.body.startswith("<svg")
