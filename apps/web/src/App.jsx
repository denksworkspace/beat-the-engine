import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Chess } from 'chess.js';

import { commitMove, createSession, evaluatePosition, getSession, saveCandidates, undoLastCommit } from './api/client';
import { CandidatePanel } from './components/CandidatePanel';
import { SessionPanel } from './components/SessionPanel';

const DRAFT_KEY = 'chess-training-draft-v1';

function buildPreviewFen(baseFen, move) {
  if (!baseFen) return '';
  const normalized = (move || '').trim();
  if (!normalized) return baseFen;

  try {
    const board = new Chess(baseFen);
    const parsed = board.move({
      from: normalized.slice(0, 2),
      to: normalized.slice(2, 4),
      promotion: normalized.slice(4, 5) || 'q',
    });
    if (!parsed) return baseFen;
    return board.fen();
  } catch {
    return baseFen;
  }
}

function isLegalMove(baseFen, move) {
  const normalized = (move || '').trim();
  if (!normalized || !baseFen) return false;

  try {
    const board = new Chess(baseFen);
    return board.moves({ verbose: true }).some((candidate) => {
      const generated = `${candidate.from}${candidate.to}${candidate.promotion || ''}`;
      return generated === normalized;
    });
  } catch {
    return false;
  }
}

function candidatePayload(candidates) {
  return candidates.map((candidate) => ({
    move: candidate.move,
    note: candidate.note || '',
    is_selected: Boolean(candidate.is_selected),
    eval_cp: typeof candidate.eval_cp === 'number' ? candidate.eval_cp : null,
    eval_source: candidate.eval_source || null,
  }));
}

function upsertCandidate(candidates, selectedMove, selectedNote) {
  const move = selectedMove.trim();
  const note = selectedNote.trim();
  const existing = candidates.find((candidate) => candidate.move === move);

  if (existing) {
    return candidates.map((candidate) =>
      candidate.move === move ? { ...candidate, note, is_selected: true } : { ...candidate, is_selected: false },
    );
  }

  return [
    ...candidates.map((candidate) => ({ ...candidate, is_selected: false })),
    {
      move,
      note,
      is_selected: true,
    },
  ];
}

function buildSessionNotice(currentSession) {
  if (!currentSession) return '';
  const modeLabel = currentSession.mode === 'challenge' ? 'Challenge' : 'Standard';
  return `${modeLabel} training session at engine level ${currentSession.engine_level}.`;
}

export default function App() {
  const [session, setSession] = useState(null);
  const [turnVersion, setTurnVersion] = useState(1);
  const [mode, setMode] = useState('standard');
  const [engineLevel, setEngineLevel] = useState(5);
  const [move, setMove] = useState('');
  const [note, setNote] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [autosaveStatus, setAutosaveStatus] = useState('');
  const [autosaveError, setAutosaveError] = useState('');
  const [retryDraft, setRetryDraft] = useState(null);

  const [evalCp, setEvalCp] = useState(null);
  const [evalSource, setEvalSource] = useState('');
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState('');

  const candidateScoreRequestRef = useRef(0);
  const lastAutosaveSignatureRef = useRef('');
  const restoredRef = useRef(false);

  const hasSession = Boolean(session);
  const baseFen = session?.fen || '';
  const hasValidMove = hasSession && isLegalMove(baseFen, move);
  const canSubmitMove = hasValidMove && !busy;
  const displayFen = useMemo(() => buildPreviewFen(baseFen, move), [baseFen, move]);
  const moveError = move.trim() && !hasValidMove ? 'Move is not legal in the current position.' : '';

  const statusLabel = useMemo(() => {
    if (busy) return `Working: ${busy}`;
    if (result) return 'Ready for next turn';
    if (hasSession) return 'Draft exploration';
    return 'Idle';
  }, [busy, hasSession, result]);

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return;

    let stored;
    try {
      stored = JSON.parse(raw);
    } catch {
      return;
    }

    if (!stored?.session_id) return;

    async function restoreSession() {
      setBusy('restoring session');
      try {
        const state = await getSession(stored.session_id);
        const serverCandidates = (state.candidates || []).map((candidate) => ({
          move: candidate.move,
          note: candidate.note,
          is_selected: candidate.is_selected,
          eval_cp: typeof candidate.eval_cp === 'number' ? candidate.eval_cp : null,
          eval_source: candidate.eval_source || null,
        }));
        const selectedServerCandidate = serverCandidates.find((candidate) => candidate.is_selected);

        setSession({
          session_id: state.session_id,
          turn_id: state.active_turn_id,
          fen: state.fen,
          mode: state.mode,
          engine_level: state.engine_level,
        });
        setMode(state.mode || 'standard');
        setEngineLevel(state.engine_level || 5);
        setTurnVersion(state.turn_version || 1);
        setCandidates(serverCandidates);
        setMove(selectedServerCandidate?.move || '');
        setNote(selectedServerCandidate?.note || '');
      } catch {
        window.localStorage.removeItem(DRAFT_KEY);
      } finally {
        setBusy('');
      }
    }

    void restoreSession();
  }, []);

  useEffect(() => {
    if (!hasSession) return;
    const payload = {
      session_id: session.session_id,
      turn_id: session.turn_id,
      fen: session.fen,
      mode: session.mode,
      engine_level: session.engine_level,
      turn_version: turnVersion,
      move,
      note,
      candidates: candidatePayload(candidates),
    };
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  }, [hasSession, session, turnVersion, move, note, candidates]);

  async function evaluateCandidate(sessionId, fenBeforeMove, targetMove) {
    const requestId = candidateScoreRequestRef.current + 1;
    candidateScoreRequestRef.current = requestId;

    const candidateFen = buildPreviewFen(fenBeforeMove, targetMove);
    let score = null;
    let scoreError = '';
    let source = 'unknown';
    try {
      const evaluated = await evaluatePosition(sessionId, candidateFen, 5.0);
      score = Number(evaluated.eval_cp);
      source = evaluated.source || 'stockfish';
    } catch (err) {
      scoreError = err.message;
    }

    if (candidateScoreRequestRef.current !== requestId) {
      return { eval_cp: null, eval_source: null, eval_error: 'stale-request' };
    }

    return {
      eval_cp: score,
      eval_source: score !== null ? source : null,
      eval_error: scoreError,
    };
  }

  useEffect(() => {
    if (!session?.session_id || !displayFen) {
      setEvalCp(null);
      setEvalSource('');
      setEvalError('');
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setEvalLoading(true);
      try {
        const evaluated = await evaluatePosition(session.session_id, displayFen, 0.25);
        if (cancelled) return;
        setEvalCp(Number(evaluated.eval_cp));
        setEvalSource(evaluated.source || 'unknown');
        setEvalError('');
      } catch (err) {
        if (cancelled) return;
        setEvalError(err.message);
      } finally {
        if (!cancelled) {
          setEvalLoading(false);
        }
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [session?.session_id, displayFen]);

  async function persistDraft(nextCandidates, options = {}) {
    if (!session) return null;
    const { blockingLabel = '', autosave = false } = options;

    if (blockingLabel) {
      setBusy(blockingLabel);
    }

    try {
      const saved = await saveCandidates(session.session_id, session.turn_id, turnVersion, candidatePayload(nextCandidates));
      setTurnVersion(saved.version);
      const savedCandidates = saved.candidates.map((candidate) => ({
        move: candidate.move,
        note: candidate.note,
        is_selected: candidate.is_selected,
        eval_cp: typeof candidate.eval_cp === 'number' ? candidate.eval_cp : null,
        eval_source: candidate.eval_source || null,
      }));
      setCandidates(savedCandidates);
      setAutosaveError('');
      setRetryDraft(null);

      return savedCandidates;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Draft save failed.';
      if (autosave) {
        setAutosaveError(message);
        setAutosaveStatus('Autosave failed. Retry available.');
      } else {
        setError(message);
      }
      setRetryDraft(nextCandidates);
      return null;
    } finally {
      if (blockingLabel) {
        setBusy('');
      }
    }
  }

  useEffect(() => {
    if (!session || !move.trim() || !hasValidMove) return;
    const nextCandidates = upsertCandidate(candidates, move, note);
    const signature = JSON.stringify(candidatePayload(nextCandidates));
    if (signature === lastAutosaveSignatureRef.current) return;

    const timer = window.setTimeout(async () => {
      setAutosaveStatus('Autosaving draft...');
      const saved = await persistDraft(nextCandidates, { autosave: true });
      if (saved) {
        lastAutosaveSignatureRef.current = signature;
        setAutosaveStatus('Draft autosaved');
      }
    }, 700);

    return () => window.clearTimeout(timer);
  }, [session, move, note, hasValidMove, turnVersion, candidates]);

  async function handleCreateSession(nextMode = mode, nextEngineLevel = engineLevel) {
    setBusy('starting session');
    setError('');
    try {
      const created = await createSession(nextMode, nextEngineLevel);
      setSession(created);
      setTurnVersion(1);
      setResult(null);
      setMove('');
      setNote('');
      setMode(nextMode);
      setEngineLevel(nextEngineLevel);
      setAutosaveStatus('');
      setAutosaveError('');
      setRetryDraft(null);
      lastAutosaveSignatureRef.current = '';
      candidateScoreRequestRef.current += 1;
      setCandidates([]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function handleSaveCandidate() {
    if (!session) return;
    const selectedMove = move.trim();
    if (!selectedMove || !hasValidMove) return;

    setError('');
    setCandidates((previous) =>
      previous.map((candidate) => ({
        ...candidate,
        eval_loading: candidate.move === selectedMove,
        eval_error: candidate.move === selectedMove ? '' : candidate.eval_error || '',
      })),
    );

    const evaluated = await evaluateCandidate(session.session_id, baseFen, selectedMove);
    const nextCandidates = upsertCandidate(candidates, selectedMove, note).map((candidate) =>
      candidate.move === selectedMove
        ? {
            ...candidate,
            eval_cp: evaluated.eval_cp,
            eval_source: evaluated.eval_source,
            eval_error: evaluated.eval_error,
            eval_loading: false,
          }
        : candidate,
    );

    const saved = await persistDraft(nextCandidates, { blockingLabel: 'saving candidate' });
    if (saved) {
      lastAutosaveSignatureRef.current = JSON.stringify(candidatePayload(saved));
      setMove('');
      setNote('');
    }
  }

  function handleSelectCandidate(candidate) {
    setMove(candidate.move);
    setNote(candidate.note || '');
    setCandidates((previous) =>
      previous.map((item) => ({
        ...item,
        is_selected: item.move === candidate.move,
      })),
    );
  }

  async function handleCommit() {
    if (!session) return;
    if (!hasValidMove) {
      setError('Cannot commit an illegal move.');
      return;
    }

    setBusy('committing move');
    setError('');
    try {
      const committed = await commitMove(session.session_id, session.turn_id, {
        selected_move: move.trim(),
        reasoning_text: note.trim(),
        version: turnVersion,
      });
      setResult(committed);
      setSession({
        ...session,
        turn_id: committed.next_turn_id,
        fen: committed.fen,
      });
      setTurnVersion(1);
      setMove('');
      setNote('');
      setAutosaveStatus('');
      setAutosaveError('');
      setRetryDraft(null);
      lastAutosaveSignatureRef.current = '';
      candidateScoreRequestRef.current += 1;
      setCandidates([]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function handleUndoLastCommit() {
    if (!session) return;
    setBusy('undoing last commit');
    setError('');
    try {
      const restored = await undoLastCommit(session.session_id);
      setSession({
        ...session,
        turn_id: restored.turn_id,
        fen: restored.fen,
      });
      setTurnVersion(restored.turn_version);
      setResult(null);
      setMove('');
      setNote('');
      setAutosaveStatus('');
      setAutosaveError('');
      setRetryDraft(null);
      lastAutosaveSignatureRef.current = '';
      candidateScoreRequestRef.current += 1;
      setCandidates([]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function handleRetryDraftSave() {
    if (!retryDraft || !session) return;
    setAutosaveError('');
    setAutosaveStatus('Retrying draft save...');
    const saved = await persistDraft(retryDraft, { blockingLabel: 'retrying draft save' });
    if (saved) {
      lastAutosaveSignatureRef.current = JSON.stringify(candidatePayload(saved));
      setAutosaveStatus('Draft save retried successfully');
    }
  }

  return (
    <div className="page-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />

      <header className="hero card rise-1">
        <p className="eyebrow">AI-Assisted Chess Reflection</p>
        <h1>Strict Training Console</h1>
        <p className="hero-text">
          Build disciplined calculation: draft candidates, commit one line, and inspect engine-grounded reflection.
        </p>
        <div className="hero-meta">
          <div>
            <span className="meta-label">State</span>
            <span className="meta-value">{statusLabel}</span>
          </div>
          <div>
            <span className="meta-label">Turn Version</span>
            <span className="meta-value">{turnVersion}</span>
          </div>
          <div>
            <span className="meta-label">Mode</span>
            <span className="meta-value">{hasSession ? session.mode : 'not started'}</span>
          </div>
        </div>
      </header>

      <section className="layout-grid">
        <SessionPanel
          session={session}
          sessionNotice={buildSessionNotice(session)}
          onCreate={handleCreateSession}
          onUndo={handleUndoLastCommit}
          busy={Boolean(busy)}
          mode={mode}
          engineLevel={engineLevel}
          onMode={setMode}
          onEngineLevel={(value) => setEngineLevel(Math.max(1, Math.min(20, Number(value) || 1)))}
        />
        <CandidatePanel
          baseFen={baseFen}
          displayFen={displayFen}
          move={move}
          note={note}
          candidates={candidates}
          onMove={setMove}
          onNote={setNote}
          onSelectCandidate={handleSelectCandidate}
          onSave={handleSaveCandidate}
          onCommit={handleCommit}
          canSave={canSubmitMove}
          canCommit={canSubmitMove}
          interactive={hasSession && !busy}
          evalCp={evalCp}
          evalLoading={evalLoading}
          evalSource={evalSource}
          evalError={evalError}
          moveError={moveError}
          autosaveStatus={autosaveStatus}
          autosaveError={autosaveError}
          retryAvailable={Boolean(retryDraft)}
          onRetrySave={handleRetryDraftSave}
        />
      </section>

      {result ? (
        <section className="card reflection-card rise-3">
          <h2>Post-Commit Reflection</h2>
          <pre className="reflection-text">{result.reflection.text}</pre>
          <div className="chips">
            {result.reflection.tags.map((tag) => (
              <span className="chip" key={tag}>
                {tag}
              </span>
            ))}
          </div>
          <div className="reflection-metrics">
            <p>
              <strong>Engine move:</strong> {result.engine_move || 'none'}
            </p>
            <p>
              <strong>Eval:</strong> {result.eval_before} {'->'} {result.eval_after}
            </p>
            <p>
              <strong>Attempts/commit:</strong> {result.metrics_snapshot.attempts_per_commit}
            </p>
          </div>
        </section>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}
    </div>
  );
}
