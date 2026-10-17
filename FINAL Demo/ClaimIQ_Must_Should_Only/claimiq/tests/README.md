# ClaimIQ pytest suite

Copy this entire `tests` folder into the root of the ClaimIQ project, replacing the existing small tests folder.

Run from the ClaimIQ project root in PyCharm terminal:

```powershell
$env:PYTHONPATH="src"
pytest -v
```

Coverage:

```powershell
$env:PYTHONPATH="src"
pytest --cov=claimiq --cov-report=term-missing
```

The suite uses SQLite for test isolation and mocks the external RAG service, so Azure OpenAI and Azure AI Search credentials are not required for these tests. The RAG tests verify ClaimIQ endpoint behavior using deterministic fakes rather than making network calls.
