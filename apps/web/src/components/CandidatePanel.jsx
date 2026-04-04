import React, { useEffect, useMemo, useState } from 'react';
import { Chess } from 'chess.js';
import { Chessboard } from 'react-chessboard';

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function formatEval(cp) {
  if (typeof cp !== 'number' || Number.isNaN(cp)) {
    return '--';
  }
  const normalized = Math.max(-9000, Math.min(9000, cp));
  const pawns = normalized / 100;
  const sign = pawns > 0 ? '+' : '';
  return `${sign}${pawns.toFixed(1)}`;
}

function evalToWhiteShare(cp) {
  if (typeof cp !== 'number' || Number.isNaN(cp)) {
    return 50;
  }
  const clamped = Math.max(-1200, Math.min(1200, cp));
  return ((clamped + 1200) / 2400) * 100;
}

function computeBoardWidth() {
  if (typeof window === 'undefined') return 430;
  return Math.max(250, Math.min(430, window.innerWidth - 90));
}

export function CandidatePanel({
  baseFen,
  displayFen,
  move,
  note,
  candidates,
  onMove,
  onNote,
  onSelectCandidate,
  onSave,
  onCommit,
  canSave,
  canCommit,
  interactive,
  evalCp,
  evalLoading,
  evalSource,
  evalError,
  moveError,
  autosaveStatus,
  autosaveError,
  onRetrySave,
  retryAvailable,
}) {
  const boardBaseFen = baseFen || DEFAULT_FEN;
  const boardFen = displayFen || boardBaseFen;
  const whiteShare = useMemo(() => evalToWhiteShare(evalCp), [evalCp]);
  const selectedArrow = move && move.length >= 4 ? [[move.slice(0, 2), move.slice(2, 4), '#0a9396']] : [];
  const [boardWidth, setBoardWidth] = useState(() => computeBoardWidth());
  const [selectedSquare, setSelectedSquare] = useState('');
  const [legalTargets, setLegalTargets] = useState([]);

  const squareStyles = useMemo(() => {
    const out = {};
    if (selectedSquare) {
      out[selectedSquare] = {
        boxShadow: 'inset 0 0 0 3px rgba(10, 147, 150, 0.9)',
      };
    }
    for (const square of legalTargets) {
      out[square] = {
        background: 'radial-gradient(circle, rgba(10,147,150,0.32) 28%, rgba(10,147,150,0) 32%)',
      };
    }
    return out;
  }, [legalTargets, selectedSquare]);

  useEffect(() => {
    function onResize() {
      setBoardWidth(computeBoardWidth());
    }

    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    setSelectedSquare('');
    setLegalTargets([]);
  }, [boardBaseFen]);

  function handleDrop(sourceSquare, targetSquare) {
    if (!interactive) return false;
    const chess = new Chess(boardBaseFen);
    const moveResult = chess.move({
      from: sourceSquare,
      to: targetSquare,
      promotion: 'q',
    });

    if (!moveResult) return false;

    const selectedMove = `${moveResult.from}${moveResult.to}${moveResult.promotion || ''}`;
    onMove(selectedMove);
    setSelectedSquare('');
    setLegalTargets([]);
    return true;
  }

  function handleSquareClick(square) {
    if (!interactive) return;
    const chess = new Chess(boardBaseFen);

    if (selectedSquare) {
      const moveResult = chess.move({
        from: selectedSquare,
        to: square,
        promotion: 'q',
      });
      if (moveResult) {
        const selectedMove = `${moveResult.from}${moveResult.to}${moveResult.promotion || ''}`;
        onMove(selectedMove);
        setSelectedSquare('');
        setLegalTargets([]);
        return;
      }
    }

    const piece = chess.get(square);
    if (!piece || piece.color !== chess.turn()) {
      setSelectedSquare('');
      setLegalTargets([]);
      return;
    }

    const targets = chess
      .moves({
        square,
        verbose: true,
      })
      .map((candidate) => candidate.to);

    if (!targets.length) {
      setSelectedSquare('');
      setLegalTargets([]);
      return;
    }

    setSelectedSquare(square);
    setLegalTargets(targets);
  }

  return (
    <section className="card panel rise-2">
      <div className="panel-header">
        <h2>Candidate Workspace</h2>
        <span className="badge">FR-1 / FR-4 / FR-5</span>
      </div>

      <div className="board-stack">
        <div className="board-frame">
          <div className="eval-bar" aria-label={`Evaluation ${formatEval(evalCp)}`}>
            <div className="eval-bar-black" style={{ height: `${100 - whiteShare}%` }} />
            <div className="eval-bar-white" style={{ height: `${whiteShare}%` }} />
            <span className="eval-text mono">{evalLoading ? '...' : formatEval(evalCp)}</span>
          </div>
          <div className="board-wrap">
            <Chessboard
              id="training-board"
              position={boardFen}
              onPieceDrop={handleDrop}
              onSquareClick={handleSquareClick}
              arePiecesDraggable={interactive}
              boardWidth={boardWidth}
              boardOrientation="white"
              customArrows={selectedArrow}
              customSquareStyles={squareStyles}
              customDarkSquareStyle={{ backgroundColor: '#4f6777' }}
              customLightSquareStyle={{ backgroundColor: '#eef2f5' }}
            />
          </div>
        </div>
        <p className="board-hint">
          {interactive
            ? 'Click a piece to see legal targets, then click a target square (drag-and-drop also works).'
            : 'Start a session to enable board interaction.'}
        </p>
        <div className="selected-move-row">
          <span className="field-label-inline">Selected move</span>
          <span className="mono">{move || 'none'}</span>
          <span className="eval-source">{evalSource || 'eval pending'}</span>
          <button className="btn btn-secondary btn-small" type="button" onClick={() => onMove('')} disabled={!move}>
            Clear
          </button>
        </div>
        {evalError ? <p className="eval-error">{evalError}</p> : null}
      </div>

      <div className="saved-candidates">
        <h3>Saved Candidates</h3>
        {candidates.length === 0 ? (
          <p className="candidate-empty">No candidates saved yet.</p>
        ) : (
          <div className="candidate-list">
            {candidates.map((candidate) => (
              <button
                key={candidate.move}
                type="button"
                className={`candidate-item ${candidate.move === move ? 'is-active' : ''}`}
                onClick={() => onSelectCandidate(candidate)}
              >
                <span className="candidate-topline">
                  <span className="candidate-move mono">{candidate.move}</span>
                  <span className="candidate-score mono">
                    {candidate.eval_loading ? 'analysing...' : candidate.eval_error ? 'error' : formatEval(candidate.eval_cp)}
                  </span>
                </span>
                <span className="candidate-note">{candidate.note || 'No description provided.'}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <label className="field-label" htmlFor="note-input">
        Candidate Description
      </label>
      <textarea
        id="note-input"
        className="text-area"
        value={note}
        onChange={(e) => onNote(e.target.value)}
        placeholder="Write your plan for the selected candidate."
      />

      <div className="actions">
        <button className="btn btn-secondary" disabled={!canSave} onClick={onSave}>
          Save Candidate
        </button>
        <button className="btn btn-primary" disabled={!canCommit} onClick={onCommit}>
          Commit Move
        </button>
      </div>
      {moveError ? <p className="eval-error">{moveError}</p> : null}
      {autosaveStatus ? <p className="autosave-status">{autosaveStatus}</p> : null}
      {autosaveError ? <p className="eval-error">{autosaveError}</p> : null}
      {retryAvailable ? (
        <button className="btn btn-secondary btn-small" type="button" onClick={onRetrySave}>
          Retry Draft Save
        </button>
      ) : null}
    </section>
  );
}
