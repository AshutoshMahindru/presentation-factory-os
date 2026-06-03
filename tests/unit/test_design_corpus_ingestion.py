import pytest

from deck_builder.design_corpus_ingestion import (
    DesignCorpusIngestionError,
    DesignCorpusIngestor,
)


def corpus_item(**overrides):
    item = {
        "source_id": "gallery-001",
        "source_uri": "https://example.test/deck",
        "title": "Investor update pattern",
        "page": 3,
        "canvas": {"width": 1200, "height": 675},
        "elements": [
            {"type": "title", "x": 96, "y": 64, "width": 520, "height": 72, "color": "#123"},
            {"type": "chart", "x": 96, "y": 180, "width": 432, "height": 320, "color": "#336699"},
            {"type": "text", "x": 624, "y": 180, "width": 400, "height": 280, "color": "#111111"},
        ],
    }
    item.update(overrides)
    return item


def test_ingestion_creates_deterministic_pattern_records_with_provenance():
    ingestor = DesignCorpusIngestor()

    first = ingestor.ingest([corpus_item()])
    second = ingestor.ingest([corpus_item()])

    assert first == second
    record = first[0]
    assert record.pattern_id.startswith("pattern_")
    assert record.source_id == "gallery-001"
    assert record.source_uri == "https://example.test/deck"
    assert record.title == "Investor update pattern"
    assert record.element_count == 3
    assert record.layout_density == "standard"
    assert record.color_tokens == ("#111111", "#112233", "#336699")
    assert record.provenance == {
        "source_id": "gallery-001",
        "source_uri": "https://example.test/deck",
        "page": 3,
        "ingestion": "deterministic_local",
    }


def test_ingestion_sorts_records_by_stable_pattern_id():
    records = DesignCorpusIngestor().ingest(
        [
            corpus_item(source_id="b-source"),
            corpus_item(source_id="a-source"),
        ]
    )

    assert [record.pattern_id for record in records] == sorted(record.pattern_id for record in records)


def test_ingestion_classifies_sparse_layout_as_spacious():
    sparse = corpus_item(
        elements=[
            {"type": "title", "x": 80, "y": 64, "width": 300, "height": 60},
            {"type": "caption", "x": 80, "y": 150, "width": 240, "height": 40},
        ]
    )

    [record] = DesignCorpusIngestor().ingest([sparse])

    assert record.layout_density == "spacious"


def test_ingestion_rejects_malformed_local_corpus_payloads():
    with pytest.raises(DesignCorpusIngestionError, match="elements"):
        DesignCorpusIngestor().ingest([corpus_item(elements=[])])

    with pytest.raises(DesignCorpusIngestionError, match="invalid element color"):
        DesignCorpusIngestor().ingest(
            [corpus_item(elements=[{"type": "shape", "x": 0, "y": 0, "width": 10, "height": 10, "color": "red"}])]
        )
