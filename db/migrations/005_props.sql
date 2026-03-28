CREATE TABLE IF NOT EXISTS props (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER REFERENCES games(id),
    sport TEXT NOT NULL,
    player_name TEXT NOT NULL,
    stat_type TEXT NOT NULL,
    line REAL NOT NULL,
    bookmaker TEXT NOT NULL,
    over_price REAL,
    under_price REAL,
    created_at DATETIME DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_props_player ON props(player_name, stat_type);
CREATE INDEX IF NOT EXISTS idx_props_sport ON props(sport);

CREATE TABLE IF NOT EXISTS prop_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER REFERENCES games(id),
    sport TEXT NOT NULL,
    player_name TEXT NOT NULL,
    stat_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    consensus_line REAL NOT NULL,
    best_line REAL NOT NULL,
    best_book TEXT NOT NULL,
    edge_pct REAL NOT NULL,
    pp_line REAL,
    created_at DATETIME DEFAULT (datetime('now'))
);
