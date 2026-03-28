-- Add outcome tracking to predictions for Brier score calibration
ALTER TABLE predictions ADD COLUMN outcome TEXT;
-- outcome values: 'win', 'loss', 'push', NULL (pending/unresolved)

-- Index to efficiently query resolved predictions
CREATE INDEX IF NOT EXISTS idx_predictions_outcome ON predictions(outcome, game_id);
