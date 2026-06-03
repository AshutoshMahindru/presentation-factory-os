from deck_builder.visual_regression import compare_decks, compare_hashes, reference_hash


def deck(headline="Base case"):
    return {
        "slides": [
            {
                "slide_id": "slide_001",
                "materiality": "high",
                "visual_quality": "code_generated",
                "content": {
                    "headline": headline,
                    "body": "Evidence-backed body.",
                    "evidence_refs": ["src_001"],
                },
            }
        ]
    }


def test_reference_hash_is_stable_for_same_deck():
    assert reference_hash(deck()) == reference_hash(deck())


def test_compare_decks_detects_drift():
    result = compare_decks(deck(), deck("Changed case"))

    assert result.passed is False
    assert result.diff_ratio > 0


def test_compare_hashes_passes_identical_hashes():
    result = compare_hashes("abc", "abc")

    assert result.passed is True
    assert result.diff_ratio == 0
