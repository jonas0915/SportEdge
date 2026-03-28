CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER REFERENCES predictions(id),
    game_id INTEGER NOT NULL REFERENCES games(id),
    sport TEXT NOT NULL,
    selection TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    odds INTEGER NOT NULL,
    stake REAL NOT NULL,
    outcome TEXT,
    pnl REAL,
    placed_at DATETIME DEFAULT (datetime('now')),
    resolved_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_bets_outcome ON bets(outcome);
CREATE INDEX IF NOT EXISTS idx_bets_sport ON bets(sport);
