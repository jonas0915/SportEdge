from abc import ABC, abstractmethod


class SportModule(ABC):
    """Base interface for sport-specific modules."""

    @property
    @abstractmethod
    def sport_key(self) -> str:
        """e.g., 'nba', 'nfl'"""

    @property
    @abstractmethod
    def espn_sport(self) -> str:
        """ESPN API sport path, e.g., 'basketball'"""

    @property
    @abstractmethod
    def espn_league(self) -> str:
        """ESPN API league path, e.g., 'nba'"""

    @property
    @abstractmethod
    def elo_k_factor(self) -> float:
        """K-factor for Elo updates. Higher = more reactive."""

    @property
    @abstractmethod
    def home_advantage(self) -> float:
        """Elo home advantage bonus (typically 50-100)."""

    @abstractmethod
    def extract_features(self, home_stats: dict, away_stats: dict) -> dict:
        """Extract normalized features for the logistic model.
        Returns dict of feature_name -> float value."""

    def team_name_map(self) -> dict[str, str]:
        """Map ESPN team names to Odds API team names if they differ.
        Override per sport as needed. Default: identity mapping."""
        return {}
