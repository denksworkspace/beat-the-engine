from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field


class ReflectRequest(BaseModel):
    selected_move: str = Field(default='', max_length=20)
    reasoning_text: str = Field(default='', max_length=2000)
    eval_before: float
    eval_after: float
    pv: str = ''
    challenge_mode: bool = False


class ReflectResponse(BaseModel):
    text: str
    tags: list[str]
    better_move: str | None = None
    status: str = 'available'
    model_version: str = 'worker-v2'


app = FastAPI(title='Chess Reflection Worker', version='1.0.0')


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.post('/reflect', response_model=ReflectResponse)
def reflect(payload: ReflectRequest) -> ReflectResponse:
    before = float(payload.eval_before)
    after = float(payload.eval_after)
    delta = round(after - before, 2)
    tags: list[str] = []

    if delta <= -120:
        tags.append('blunder')
    elif delta < 0:
        tags.append('tactic')
    else:
        tags.append('positional')

    if payload.challenge_mode and len(payload.reasoning_text.strip()) < 20:
        tags.append('timing')

    if delta >= 80:
        grade = 'Brilliant'
    elif delta >= 40:
        grade = 'Excellent'
    elif delta >= 0:
        grade = 'Good'
    elif delta > -80:
        grade = 'Inaccuracy'
    elif delta > -180:
        grade = 'Mistake'
    else:
        grade = 'Blunder'

    idea = payload.reasoning_text.strip() or 'No idea provided.'
    if len(idea) < 20:
        flow_audit = 'Reasoning depth is weak: the move may be good, but the idea was not explained concretely.'
    elif delta >= 0:
        flow_audit = 'Reasoning flow is coherent: your stated idea matches the observed engine outcome.'
    else:
        flow_audit = 'Reasoning flow is inconsistent: the stated idea does not match the resulting engine evaluation.'

    strengths = (
        'The move preserved or improved evaluation and kept positional structure stable.'
        if delta >= 0
        else 'The move still reflects an understandable strategic intention in the current position.'
    )
    risks = (
        'No critical tactical weakness was detected for this exact move.'
        if delta >= 0
        else 'This move introduced a measurable tactical or positional liability in the current position.'
    )
    engine_note = (
        'Engine rates the played move as stable in this exact position.'
        if delta >= 0
        else 'Engine rates the played move as inferior in this exact position.'
    )

    text = (
        '### Post-Commit Reflection\n\n'
        f'**Move Used:** `{payload.selected_move or "unknown"}`\n'
        f'**Idea Stated:** {idea}\n'
        f'**Position Outcome:** {grade} (eval {before:.1f} -> {after:.1f}, delta {delta:+.1f} cp)\n\n'
        '#### Idea Flow Audit\n'
        f'- {flow_audit}\n\n'
        '#### Current-Move Risks\n'
        f'- {risks}\n\n'
        '#### Current-Move Strengths\n'
        f'- {strengths}\n\n'
        f'**Engine Note:** {engine_note}'
    )

    return ReflectResponse(
        text=text[:800],
        tags=tags,
        better_move=None,
        status='available',
        model_version='worker-v2',
    )
