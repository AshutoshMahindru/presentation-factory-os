from api.exports import SUPPORTED_FORMATS, export_deck
from tool_server.export import build_export_response


def deck():
    return {
        "slides": [
            {
                "slide_id": "slide_001",
                "materiality": "high",
                "visual_quality": "code_generated",
                "speaker_notes": "Open with the retention proof.",
                "content": {
                    "headline": "Retention creates pricing power",
                    "body": "Expansion is supported by cohort evidence.",
                    "evidence_refs": ["src_001"],
                },
            }
        ]
    }


def test_multi_format_export_builds_all_local_artifact_contracts():
    result = export_deck(deck())

    assert result["metadata_type"] == "multi_format_export"
    assert tuple(result["formats"]) == SUPPORTED_FORMATS
    assert {artifact["format"] for artifact in result["artifacts"]} == set(SUPPORTED_FORMATS)
    assert all(artifact["content_hash"] for artifact in result["artifacts"])


def test_tool_server_export_response_limits_formats():
    result = build_export_response(deck(), formats=["web", "speaker_notes"])

    assert result["formats"] == ["web", "speaker_notes"]
