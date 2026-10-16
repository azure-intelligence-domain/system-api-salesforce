# CLAUDE.md

The Salesforce System API: orders as the (simulated) Salesforce keeps them, in the platform's
contract. Owned by the **sales team**. Ground rules live in the
[ai-intelligence-domain](https://github.com/azure-intelligence-domain/ai-intelligence-domain)
repository (ADR 0007 source systems, ADR 0014 process layer split).

- A System API translates, it does not decide: no order rules here (status transitions belong to
  the Order Process API). It stores what it is given and computes only what Salesforce computes
  (`OrderNumber`, `TotalAmount`, `Status`, dates).
- Salesforce's data model and naming stay in `salesforce.py`; everything else speaks the contract.
- Contract first: `openapi.yaml` changes before the code, with a higher `info.version`. Request
  bodies are validated against `openapi.yaml` itself (`contract.py`).
- Only the people gateway's managed identity gets past Easy Auth; callers reach it through the
  gateway's `system-apis` product, if they are on `integration-platform/routing/internal-callers.yaml`.
- Tests: `uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest pytest -q`
