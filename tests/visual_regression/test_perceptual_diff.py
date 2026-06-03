from deck_builder.visual_regression import compare_decks


def test_perceptual_diff_contract_is_deterministic_hash_diff():
    deck = {
        "slides": [
            {
                "slide_id": "slide_001",
                "materiality": "low",
                "visual_quality": "code_generated",
                "content": {"headline": "Appendix", "body": "Reference detail."},
            }
        ]
    }

    assert compare_decks(deck, deck).passed is True
