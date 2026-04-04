import React from 'react';

export function SessionPanel({ session, sessionNotice, onCreate, onUndo, busy, mode, engineLevel, onMode, onEngineLevel }) {
  return (
    <section className="card panel rise-2">
      <div className="panel-header">
        <h2>Session Control</h2>
        <span className="badge">solo mode</span>
      </div>

      {!session ? (
        <div className="panel-empty">
          <p>Initialize a training session to unlock candidate drafting and move commitment.</p>
          <div className="field-stack">
            <label className="field-label" htmlFor="mode-select">
              Mode
            </label>
            <select
              id="mode-select"
              className="input-control"
              value={mode}
              onChange={(e) => onMode(e.target.value)}
              disabled={busy}
            >
              <option value="standard">standard</option>
              <option value="challenge">challenge</option>
            </select>
          </div>
          <div className="field-stack">
            <label className="field-label" htmlFor="engine-level-input">
              Engine Level (1-20)
            </label>
            <input
              id="engine-level-input"
              className="input-control"
              type="number"
              min={1}
              max={20}
              value={engineLevel}
              onChange={(e) => onEngineLevel(Number(e.target.value || 1))}
              disabled={busy}
            />
          </div>
          <button className="btn btn-primary" onClick={() => onCreate(mode, engineLevel)} disabled={busy}>
            {busy ? 'Starting...' : 'Start Training Session'}
          </button>
        </div>
      ) : (
        <>
          <dl className="key-values">
            <div>
              <dt>Session</dt>
              <dd>{sessionNotice || 'Active training session'}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>Ready for candidate exploration</dd>
            </div>
            <div>
              <dt>Current FEN</dt>
              <dd className="mono fen-value" title={session.fen}>
                {session.fen}
              </dd>
            </div>
          </dl>
          <div className="session-actions">
            <button className="btn btn-secondary" type="button" onClick={onUndo} disabled={busy}>
              Undo Last Commit
            </button>
          </div>
        </>
      )}
    </section>
  );
}
