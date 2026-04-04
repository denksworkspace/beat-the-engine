from __future__ import annotations

import re

import httpx

from app.core.config import get_settings


class ReflectionWorkerClient:
    REQUIRED_HEADINGS = [
        '### Post-Commit Reflection',
        '#### Idea Flow Audit',
        '#### Current-Move Risks',
        '#### Current-Move Strengths',
        '**Engine Note:**',
    ]
    FORBIDDEN_PATTERNS = [
        '#### Better Move',
        '#### Next',
        '#### Training',
        'checklist',
        'next move',
        'before committing',
        'you should',
        'consider',
        'try ',
    ]

    def __init__(self) -> None:
        self.settings = get_settings()

    def reflect(self, reasoning_text: str, analysis: dict, challenge_mode: bool) -> dict:
        payload = {
            'selected_move': str(analysis.get('selected_move', '')),
            'reasoning_text': reasoning_text,
            'eval_before': analysis['eval_before'],
            'eval_after': analysis['eval_after'],
            'pv': analysis.get('pv', ''),
            'challenge_mode': challenge_mode,
        }
        try:
            with httpx.Client(timeout=min(float(self.settings.reflection_timeout_seconds), 3.0)) as client:
                response = client.post(f'{self.settings.reflection_worker_url}/reflect', json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return self._sanitize(data, reasoning_text, analysis)
        except Exception:
            pass
        return self._local_reflection(reasoning_text, analysis, challenge_mode)

    def _sanitize(self, data: dict, reasoning_text: str, analysis: dict) -> dict:
        raw_text = str(data.get('text', '')).strip()
        # Keep reflection payload safe for plain rendering and bounded in size.
        text = re.sub(r'<[^>]*>', '', raw_text)[: self.settings.max_reflection_length]
        tags = [str(t).strip().lower() for t in data.get('tags', []) if str(t).strip()]
        tags = self._ensure_classification_tags(tags, analysis.get('eval_before'), analysis.get('eval_after'))
        if not self._is_valid_worker_reflection(text):
            text = self._structured_reflection(
                reasoning_text=reasoning_text,
                analysis=analysis,
                better_move=data.get('better_move'),
                fallback_text=text,
            )
        model_version = str(data.get('model_version', '')).strip() or 'worker-v1'
        return {
            'text': text[: self.settings.max_reflection_length],
            'tags': tags[:5],
            'better_move': None,
            'status': data.get('status', 'available'),
            'model_version': model_version[:64],
        }

    def _local_reflection(self, reasoning_text: str, analysis: dict, challenge_mode: bool) -> dict:
        delta = round(float(analysis['eval_after']) - float(analysis['eval_before']), 2)
        tags: list[str] = []
        if delta <= -120:
            tags.append('blunder')
        elif delta < 0:
            tags.append('tactic')
        else:
            tags.append('positional')
        if challenge_mode and len((reasoning_text or '').strip()) < 20:
            tags.append('timing')
        text = self._structured_reflection(
            reasoning_text=reasoning_text,
            analysis=analysis,
            better_move=None,
            fallback_text='No worker reflection text.',
        )
        return {
            'text': text[: self.settings.max_reflection_length],
            'tags': self._ensure_classification_tags(tags, analysis.get('eval_before'), analysis.get('eval_after')),
            'better_move': None,
            'status': 'available',
            'model_version': 'local-v1',
        }

    def _structured_reflection(self, reasoning_text: str, analysis: dict, better_move: str | None, fallback_text: str) -> str:
        before = float(analysis.get('eval_before', 0.0))
        after = float(analysis.get('eval_after', 0.0))
        delta = after - before

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

        idea_used = (reasoning_text or '').strip() or 'No idea provided.'
        selected_move = str(analysis.get('selected_move', '')).strip() or 'unknown'
        if len(idea_used) < 20:
            flow_audit = 'Reasoning depth is weak: the move result is known, but the decision logic was not justified.'
        elif delta >= 0:
            flow_audit = 'Reasoning flow is coherent: the stated idea matches the observed evaluation outcome.'
        else:
            flow_audit = 'Reasoning flow is inconsistent: the stated idea does not match the observed evaluation outcome.'

        if delta >= 0:
            good_part = 'The move preserved or improved evaluation while keeping structure stable in this position.'
            bad_part = 'No critical tactical weakness appears in this exact played move.'
            engine_note = 'Engine evaluates the played move as stable in this exact position.'
        else:
            good_part = 'The move still reflects an understandable positional intention in this position.'
            bad_part = 'This exact move loses evaluation and introduces a tactical or positional liability.'
            engine_note = 'Engine evaluates the played move as inferior in this exact position.'

        return (
            '### Post-Commit Reflection\n\n'
            f'**Move Used:** `{selected_move}`\n'
            f'**Idea Stated:** {idea_used}\n'
            f'**Position Outcome:** {grade} (eval {before:.1f} -> {after:.1f}, delta {delta:+.1f} cp)\n\n'
            '#### Idea Flow Audit\n'
            f'- {flow_audit}\n\n'
            '#### Current-Move Risks\n'
            f'- {bad_part}\n\n'
            '#### Current-Move Strengths\n'
            f'- {good_part}\n\n'
            f'**Engine Note:** {self._one_sentence(engine_note, fallback_text)}'
        )

    def _one_sentence(self, primary: str, fallback: str) -> str:
        source = (primary or '').strip() or (fallback or '').strip() or 'No additional note.'
        source = re.sub(r'\s+', ' ', source)
        match = re.search(r'[.!?]', source)
        if not match:
            return source
        return source[: match.end()].strip()

    def _is_valid_worker_reflection(self, text: str) -> bool:
        if not text:
            return False
        if len(text.split()) < 45:
            return False
        lowered = text.lower()
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern.lower() in lowered:
                return False

        last_pos = -1
        for heading in self.REQUIRED_HEADINGS:
            count = text.count(heading)
            if count != 1:
                return False
            pos = text.find(heading)
            if pos <= last_pos:
                return False
            last_pos = pos

        engine_note_idx = text.find('**Engine Note:**')
        if engine_note_idx < 0:
            return False
        engine_note = text[engine_note_idx + len('**Engine Note:**') :].strip()
        if not engine_note:
            return False
        if '\n' in engine_note:
            return False
        if sum(engine_note.count(p) for p in ['.', '!', '?']) > 1:
            return False
        return True

    def _ensure_classification_tags(
        self, tags: list[str], eval_before: float | int | None, eval_after: float | int | None
    ) -> list[str]:
        normalized = [tag for tag in tags if tag]
        classified = {'blunder', 'tactic', 'positional'}
        if any(tag in classified for tag in normalized):
            return normalized

        try:
            before = float(eval_before if eval_before is not None else 0.0)
            after = float(eval_after if eval_after is not None else 0.0)
        except (TypeError, ValueError):
            before = 0.0
            after = 0.0

        delta = after - before
        if delta <= -120:
            normalized.append('blunder')
        elif delta < 0:
            normalized.append('tactic')
        else:
            normalized.append('positional')
        return normalized
