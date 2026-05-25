# Retrieval Router Classifier

## Purpose

`RetrievalRouter` uses a small pluggable classifier to choose the retrieval
mode for incoming queries while preserving the standard context payload schema.

The classifier emits one of these query classes:

- `financial`
- `strategic`
- `narrative`
- `visual`
- `unknown`

The router maps those classes to existing retrieval modes:

- `financial` -> `structured`
- `strategic` -> `hybrid`
- `narrative` -> `semantic`
- `visual` -> `semantic`
- `unknown` -> `hybrid`

Caller-supplied mode hints are still honored, including `graph`.

## Local Classifier

The default `QueryClassifier` is a deterministic local fallback implemented by
`DeterministicRoutingClassifier`. It vectorizes the query and curated class
profiles with normalized tokens, adjacent token pairs, and small character
ngrams, then selects the strongest cosine-similarity match when the score clears
the local confidence threshold.

This avoids raw keyword-count routing and keeps tests independent of remote LLM
API keys.

## LiteLLM Embeddings

PFOS has LiteLLM proxy configuration for local embeddings, but this repository
does not currently include a locally testable embedding client dependency or a
unit-test harness for the proxy. Baby Step 94 therefore keeps embeddings
inactive in tests and uses the deterministic classifier through the pluggable
`RetrievalQueryClassifier` protocol.

Future embedding-backed routing can implement the same protocol without changing
`RetrievalRouter` payload behavior.

## Unknown Queries

Low-confidence or out-of-scope queries classify as `unknown`. The router keeps
the existing defensive behavior by forcing `hybrid` retrieval, adding a
`scope_mismatch` gap in empty payloads, and returning a recommended next action
that asks for a more specific query or broad retrieval with gaps.

## Validation

```bash
python3 -m compileall retrieval_engine
python3 -m pytest tests/unit/test_retrieval_router_classifier.py -vv
python3 -m pytest tests/unit/test_retrieval_payload_schema.py -vv
make validate
```
