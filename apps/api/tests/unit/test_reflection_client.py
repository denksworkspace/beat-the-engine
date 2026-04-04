from app.workers.reflection_client import ReflectionWorkerClient


def test_sanitize_bounds_and_removes_html() -> None:
    client = ReflectionWorkerClient()
    payload = client._sanitize(
        {
            'text': '<b>Great move</b><script>alert(1)</script>',
            'tags': [],
            'eval_before': 20,
            'eval_after': -200,
            'model_version': 'worker-alpha',
        },
        reasoning_text='',
        analysis={'eval_before': 20, 'eval_after': -200, 'selected_move': 'e2e4'},
    )
    assert '<' not in payload['text']
    assert 'blunder' in payload['tags']
    assert payload['model_version'] == 'worker-alpha'


def test_local_reflection_classifies_move() -> None:
    client = ReflectionWorkerClient()
    payload = client._local_reflection(
        reasoning_text='',
        analysis={'eval_before': 15, 'eval_after': 40, 'pv': 'e7e5'},
        challenge_mode=False,
    )
    assert any(tag in {'positional', 'tactic', 'blunder'} for tag in payload['tags'])
    assert payload['model_version'] == 'local-v1'
    assert '### Post-Commit Reflection' in payload['text']
    assert '#### Idea Flow Audit' in payload['text']
    assert '#### Current-Move Risks' in payload['text']
    assert '#### Current-Move Strengths' in payload['text']
    assert '**Engine Note:**' in payload['text']
    assert '#### Better Move' not in payload['text']


def test_worker_payload_is_normalized_to_strict_reflection_structure() -> None:
    client = ReflectionWorkerClient()
    markdown = (
        '### Post-Commit Reflection\n\n'
        '**Move Used:** `e2e4`\n'
        '**Idea Stated:** Control center and speed development.\n'
        '**Position Outcome:** Good (eval 35.0 -> 40.0, delta +5.0 cp)\n\n'
        '#### Idea Flow Audit\n'
        '- The idea is coherent with the result.\n\n'
        '#### Current-Move Risks\n'
        '- No critical tactical weakness detected in this played move.\n\n'
        '#### Current-Move Strengths\n'
        '- The move keeps central control and stable development.\n\n'
        '**Engine Note:** Engine rates the played move as stable in the current position.'
    )
    payload = client._sanitize(
        {
            'text': markdown,
            'tags': ['tactic'],
            'better_move': 'd7d5',
            'model_version': 'worker-v2',
        },
        reasoning_text='Control dark squares and challenge center',
        analysis={'eval_before': 35.0, 'eval_after': -70.0, 'selected_move': 'e2e4'},
    )
    assert payload['model_version'] == 'worker-v2'
    assert payload['better_move'] is None
    assert payload['text'].startswith('### Post-Commit Reflection')
    assert payload['text'].count('**Engine Note:**') == 1
    assert '#### Idea Flow Audit' in payload['text']
    assert 'e2e4' in payload['text']


def test_invalid_worker_reflection_falls_back_to_local_structure() -> None:
    client = ReflectionWorkerClient()
    payload = client._sanitize(
        {
            'text': '1) Idea Used only',
            'tags': [],
            'better_move': 'd7d5',
            'model_version': 'worker-v2',
        },
        reasoning_text='Develop and control center',
        analysis={'eval_before': 10.0, 'eval_after': -90.0, 'selected_move': 'e2e4'},
    )
    assert payload['text'].startswith('### Post-Commit Reflection')
    assert payload['text'].count('**Engine Note:**') == 1


def test_worker_reflection_with_hints_is_rejected_and_falls_back() -> None:
    client = ReflectionWorkerClient()
    payload = client._sanitize(
        {
            'text': (
                '### Post-Commit Reflection\n\n'
                '**Move Used:** `e2e4`\n'
                '**Idea Stated:** center\n'
                '**Position Outcome:** Good\n\n'
                '#### Idea Flow Audit\n- ok\n\n'
                '#### Current-Move Risks\n- ok\n\n'
                '#### Current-Move Strengths\n- ok\n\n'
                '#### Better Move (Engine)\n- d7d5\n\n'
                '**Engine Note:** You should play this next.'
            ),
            'tags': ['positional'],
            'better_move': 'd7d5',
            'model_version': 'worker-v2',
        },
        reasoning_text='Control center',
        analysis={'eval_before': 10.0, 'eval_after': 20.0, 'selected_move': 'e2e4'},
    )
    assert payload['text'].startswith('### Post-Commit Reflection')
    assert '#### Better Move' not in payload['text']


def test_reflect_caps_timeout_to_three_seconds(monkeypatch) -> None:
    captured = {'timeout': None}

    class _DummyResponse:
        status_code = 503

        def json(self):  # type: ignore[no-untyped-def]
            return {}

    class _DummyClient:
        def __init__(self, timeout):  # type: ignore[no-untyped-def]
            captured['timeout'] = timeout

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def post(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return _DummyResponse()

    monkeypatch.setattr('app.workers.reflection_client.httpx.Client', _DummyClient)
    client = ReflectionWorkerClient()
    client.settings.reflection_timeout_seconds = 9.5
    client.reflect('note', {'eval_before': 0, 'eval_after': 1, 'pv': ''}, False)
    assert captured['timeout'] == 3.0
