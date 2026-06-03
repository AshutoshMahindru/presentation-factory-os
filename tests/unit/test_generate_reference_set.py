from scripts.generate_reference_set import generate_reference_set


def test_generate_reference_set_sorts_names_and_hashes_decks():
    decks = {
        "b": {"slides": [{"slide_id": "b", "content": {"headline": "B"}}]},
        "a": {"slides": [{"slide_id": "a", "content": {"headline": "A"}}]},
    }

    references = generate_reference_set(decks)

    assert list(references) == ["a", "b"]
    assert references["a"] != references["b"]
