CREATE TABLE IF NOT EXISTS team_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    team_name TEXT NOT NULL,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    wins_l10 INTEGER DEFAULT 0,
    losses_l10 INTEGER DEFAULT 0,
    home_wins INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    points_for REAL DEFAULT 0,
    points_against REAL DEFAULT 0,
    streak INTEGER DEFAULT 0,
    rest_days INTEGER DEFAULT 1,
    injuries_json TEXT DEFAULT '[]',
    extra_json TEXT DEFAULT '{}',
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(sport, team_name)
);

CREATE INDEX IF NOT EXISTS idx_team_stats_sport ON team_stats(sport, team_name);

CREATE TABLE IF NOT EXISTS elo_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    team_name TEXT NOT NULL,
    rating REAL NOT NULL DEFAULT 1500.0,
    games_played INTEGER DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(sport, team_name)
);

CREATE INDEX IF NOT EXISTS idx_elo_sport ON elo_ratings(sport, team_name);
