# ClaimIQ - Must and Should Scope Only

This source code implements only the Must and Should functional requirements from the supplied SRS. It excludes Could and optional features.

## Included requirements

- FR-001 user and role administration
- FR-002 document upload
- FR-003 claim creation
- FR-004 claim status updates and notes
- FR-005 controlled claim workflow
- FR-006 search by policy number, claimant and status
- FR-007 RAG questions over approved documents
- FR-008 source citations
- FR-009 Manager analytics
- FR-010 turnaround and approval-rate metrics
- FR-011 role and region-based visibility
- FR-012 append-only claim status history
- FR-013 AI query logs
- FR-015 SLA breach count
- FR-016 document activation and deactivation
- FR-017 required-field validation
- FR-018 OpenAPI/Swagger

## Explicitly excluded

- FR-014 analytics filters by date range, region and claim type because it is Could
- API gateway
- Key Vault
- Application Insights
- Front Door or Application Gateway
- Entra ID and enterprise SSO
- Redis caching
- fraud scoring
- background ingestion workers
- SLA notifications
- payment processing
- mobile application
- multilingual support

Azure OpenAI and Azure AI Search are used only to satisfy the required RAG capability. Uploaded originals are stored in the local `uploads` directory.

## Run in PyCharm Community Edition

1. Open this folder in PyCharm.
2. Create a Python 3.11 virtual environment.
3. Install packages:

```powershell
python -m pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and fill only Azure OpenAI and Azure AI Search values.
5. Start PostgreSQL:

```powershell
docker compose up -d db
```

6. Create the Azure AI Search index:

```powershell
$env:PYTHONPATH="src"
python scripts/create_search_index.py
```

7. Seed users and policy:

```powershell
python scripts/seed.py
```

8. Start the API:

```powershell
python -m uvicorn claimiq.main:app --reload --host 0.0.0.0 --port 8000
```

9. Open `http://localhost:8000/docs`.

Initial password for `admin`, `manager`, `adjuster`, and `support`: `ChangeMe123!`.

## Test

```powershell
$env:PYTHONPATH="src"
pytest --cov=claimiq
```
