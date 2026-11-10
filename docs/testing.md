# Testing

## Backend

From `backend`, with the Python environment activated:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Tests use temporary files/databases and mocked model or network responses. They cover:

- PDF identity, passage verification, parsing caches, uploads, and reuse.
- Literature screening, source relevance, and structured response handling.
- Experiment facts, conservative linking, and researcher comparisons.
- Concurrent role requests, source references, questions, and action IDs.
- Draft rules, confirmation, revocation, persistence, and revision conflicts.
- Model-client caching and the existing elicitation/routing API contracts.

To run just the board tests:

```bash
python -m unittest discover -s tests -p "test_research_board.py"
```

## Frontend

From `frontend`:

```bash
npm test
npx tsc --noEmit
npm run build
```

The Node tests cover preparation order and partial failures, stale updates, query autosaving, saved template restoration, source display, and stable workspace identity.

For a manual check, open `/examples/itaconate`, select a result, inspect its source passage, and switch between evidence, perspectives, and overview. Saving and regeneration are disabled in this example. In a live project, check that a draft leaves eligibility unchanged, confirmation applies it, and revocation restores it.

These checks verify software behavior. The bundled example is a source-reviewed walkthrough, documented in [example provenance](example-project.md).
