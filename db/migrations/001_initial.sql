CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    league TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    start_time DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    home_score INTEGER,
    away_score INTEGER,
    winner TEXT,
    api_id TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    bookmaker TEXT NOT NULL,
    bet_type TEXT NOT NULL,
    selection TEXT NOT NULL,
    price REAL NOT NULL,
    point REAL,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_odds_game_time ON odds(game_id, timestamp);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    bet_type TEXT NOT NULL,
    selection TEXT NOT NULL,
    model_prob REAL NOT NULL,
    market_prob REAL NOT NULL,
    edge REAL NOT NULL,
    confidence REAL NOT NULL,
    kelly_fraction REAL NOT NULL,
    score REAL NOT NULL,
    rationale TEXT,
    best_book TEXT,
    best_odds REAL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions(game_id, created_at);

CREATE TABLE IF NOT EXISTS credit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credits INTEGER NOT NULL,
    sport TEXT,
    spent_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
