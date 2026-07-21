# Contributing

Use Python 3.12+, keep provider-specific code inside `app/llm`, and preserve the tenant and
approval boundaries. Never add real industrial records, personal data, API keys, or credentials.

Before opening a pull request:

```bash
python -m pip install -e ".[all,dev]"
ruff format .
ruff check .
mypy app dashboard evals scripts
pytest -m "not live"
```

Add deterministic tests for behavior changes. Paid provider tests must use the `live` marker and
remain excluded by default. Update the versioned evaluation dataset or report when making an
optimization claim.
