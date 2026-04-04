# WAT (Workflows, Agents, Tools)

## Workflow
1. Read PRD + scenario IDs.
2. Map scenario to system layer.
3. Implement minimal change in one layer.
4. Run tests.
5. Fix root cause.
6. Repeat until green.

## Agents
- Planner: maps scenario to tasks.
- Implementer: applies code changes in one layer.
- Verifier: runs tests and confirms contract compatibility.

## Tools
- API server (`uvicorn`)
- Database (`postgres` / sqlite for tests)
- Pytest suites (unit/integration/e2e)
- Docker Compose for reproducible environment
