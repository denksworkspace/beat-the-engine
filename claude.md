# Agent Rules for This Project

## Source of Truth
- Product behavior: `prd.json` and `chess_app_spec_filled.xlsx`.
- Validation behavior: `Test Strategy Template - Chess App Filled.docx` and tests.

## Architecture Constraints
- Keep strict layering: API -> Service -> Repository -> Model.
- `apps/web` is a client only. No direct DB logic in UI.
- Bot/Web clients talk to backend API contracts only.

## Forbidden Actions
- Do not edit tests to force green output.
- Do not bypass service layer by writing business rules in routes or repositories.
- Do not remove error codes or contract fields used by tests.

## Validation Loop
- Red -> Green -> Refactor.
- Apply minimal patch per failing test.
- Rerun relevant unit/integration/e2e checks after each patch.
