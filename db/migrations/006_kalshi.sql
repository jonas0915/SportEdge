CREATE TABLE IF NOT EXISTS kalshi_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    event_ticker TEXT,
    title TEXT NOT NULL,
    category TEXT,
    status TEXT DEFAULT 'open',
    yes_price REAL,
    no_price REAL,
    volume INTEGER DEFAULT 0,
    volume_24h INTEGER DEFAULT 0,
    open_interest INTEGER DEFAULT 0,
    close_time TEXT,
    updated_at DATETIME DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kalshi_category ON kalshi_markets(category);
CREATE INDEX IF NOT EXISTS idx_kalshi_status ON kalshi_markets(status);
