"""
Kalshi edge finder.

For sports markets: compare Kalshi implied probability against SportEdge
model probabilities to surface mispriced contracts.

For non-sports markets: no edge calculation — just display the market data.
"""
import logging
import re
from db.models import get_kalshi_markets, get_top_picks

logger = logging.getLogger("engine.kalshi_edge")

# Map common team name fragments to canonical lookup strings.
# Kalshi tickers often include the team city or nickname in all-caps.
# E.g. KXNBA-26-CELTICS, KXNFL-26-CHIEFS, KXMLB-26-YANKEES
_TEAM_ALIASES: dict[str, list[str]] = {
    # NBA
    "celtics": ["Boston Celtics", "Celtics"],
    "lakers": ["Los Angeles Lakers", "Lakers"],
    "warriors": ["Golden State Warriors", "Warriors"],
    "nuggets": ["Denver Nuggets", "Nuggets"],
    "bucks": ["Milwaukee Bucks", "Bucks"],
    "heat": ["Miami Heat", "Heat"],
    "sixers": ["Philadelphia 76ers", "76ers", "Sixers"],
    "suns": ["Phoenix Suns", "Suns"],
    "clippers": ["LA Clippers", "Clippers"],
    "nets": ["Brooklyn Nets", "Nets"],
    "knicks": ["New York Knicks", "Knicks"],
    "bulls": ["Chicago Bulls", "Bulls"],
    "cavaliers": ["Cleveland Cavaliers", "Cavaliers", "Cavs"],
    "hawks": ["Atlanta Hawks", "Hawks"],
    "raptors": ["Toronto Raptors", "Raptors"],
    "magic": ["Orlando Magic", "Magic"],
    "pacers": ["Indiana Pacers", "Pacers"],
    "pistons": ["Detroit Pistons", "Pistons"],
    "hornets": ["Charlotte Hornets", "Hornets"],
    "wizards": ["Washington Wizards", "Wizards"],
    "thunder": ["Oklahoma City Thunder", "Thunder"],
    "spurs": ["San Antonio Spurs", "Spurs"],
    "mavericks": ["Dallas Mavericks", "Mavericks", "Mavs"],
    "rockets": ["Houston Rockets", "Rockets"],
    "grizzlies": ["Memphis Grizzlies", "Grizzlies"],
    "pelicans": ["New Orleans Pelicans", "Pelicans"],
    "jazz": ["Utah Jazz", "Jazz"],
    "timberwolves": ["Minnesota Timberwolves", "Timberwolves", "Wolves"],
    "blazers": ["Portland Trail Blazers", "Trail Blazers", "Blazers"],
    "kings": ["Sacramento Kings", "Kings"],
    # NFL
    "chiefs": ["Kansas City Chiefs", "Chiefs"],
    "eagles": ["Philadelphia Eagles", "Eagles"],
    "patriots": ["New England Patriots", "Patriots"],
    "cowboys": ["Dallas Cowboys", "Cowboys"],
    "packers": ["Green Bay Packers", "Packers"],
    "49ers": ["San Francisco 49ers", "49ers"],
    "ravens": ["Baltimore Ravens", "Ravens"],
    "bills": ["Buffalo Bills", "Bills"],
    "bengals": ["Cincinnati Bengals", "Bengals"],
    "browns": ["Cleveland Browns", "Browns"],
    "steelers": ["Pittsburgh Steelers", "Steelers"],
    "jets": ["New York Jets", "Jets"],
    "giants": ["New York Giants", "Giants"],
    "dolphins": ["Miami Dolphins", "Dolphins"],
    "commanders": ["Washington Commanders", "Commanders"],
    "colts": ["Indianapolis Colts", "Colts"],
    "texans": ["Houston Texans", "Texans"],
    "jaguars": ["Jacksonville Jaguars", "Jaguars"],
    "titans": ["Tennessee Titans", "Titans"],
    "broncos": ["Denver Broncos", "Broncos"],
    "raiders": ["Las Vegas Raiders", "Raiders"],
    "chargers": ["Los Angeles Chargers", "Chargers"],
    "seahawks": ["Seattle Seahawks", "Seahawks"],
    "rams": ["Los Angeles Rams", "Rams"],
    "cardinals": ["Arizona Cardinals", "Cardinals"],
    "falcons": ["Atlanta Falcons", "Falcons"],
    "panthers": ["Carolina Panthers", "Panthers"],
    "saints": ["New Orleans Saints", "Saints"],
    "buccaneers": ["Tampa Bay Buccaneers", "Buccaneers", "Bucs"],
    "lions": ["Detroit Lions", "Lions"],
    "vikings": ["Minnesota Vikings", "Vikings"],
    "bears": ["Chicago Bears", "Bears"],
    # MLB
    "yankees": ["New York Yankees", "Yankees"],
    "mets": ["New York Mets", "Mets"],
    "redsox": ["Boston Red Sox", "Red Sox"],
    "dodgers": ["Los Angeles Dodgers", "Dodgers"],
    "cubs": ["Chicago Cubs", "Cubs"],
    "whitesox": ["Chicago White Sox", "White Sox"],
    "astros": ["Houston Astros", "Astros"],
    "braves": ["Atlanta Braves", "Braves"],
    "phillies": ["Philadelphia Phillies", "Phillies"],
    "cardinals": ["St. Louis Cardinals", "Cardinals"],
    "giants": ["San Francisco Giants", "Giants"],
    "padres": ["San Diego Padres", "Padres"],
    "mariners": ["Seattle Mariners", "Mariners"],
    "athletics": ["Oakland Athletics", "Athletics", "A's"],
    "angels": ["Los Angeles Angels", "Angels"],
    "rangers": ["Texas Rangers", "Rangers"],
    "twins": ["Minnesota Twins", "Twins"],
    "tigers": ["Detroit Tigers", "Tigers"],
    "guardians": ["Cleveland Guardians", "Guardians"],
    "royals": ["Kansas City Royals", "Royals"],
    "brewers": ["Milwaukee Brewers", "Brewers"],
    "pirates": ["Pittsburgh Pirates", "Pirates"],
    "reds": ["Cincinnati Reds", "Reds"],
    "bluejays": ["Toronto Blue Jays", "Blue Jays"],
    "orioles": ["Baltimore Orioles", "Orioles"],
    "rays": ["Tampa Bay Rays", "Rays"],
    "nationals": ["Washington Nationals", "Nationals"],
    "marlins": ["Miami Marlins", "Marlins"],
    "rockies": ["Colorado Rockies", "Rockies"],
    "diamondbacks": ["Arizona Diamondbacks", "Diamondbacks", "D-backs"],
    # NHL
    "bruins": ["Boston Bruins", "Bruins"],
    "canucks": ["Vancouver Canucks", "Canucks"],
    "leafs": ["Toronto Maple Leafs", "Maple Leafs", "Leafs"],
    "canadiens": ["Montreal Canadiens", "Canadiens", "Habs"],
    "rangers": ["New York Rangers", "Rangers"],
    "islanders": ["New York Islanders", "Islanders"],
    "devils": ["New Jersey Devils", "Devils"],
    "flyers": ["Philadelphia Flyers", "Flyers"],
    "penguins": ["Pittsburgh Penguins", "Penguins"],
    "caps": ["Washington Capitals", "Capitals"],
    "hurricanes": ["Carolina Hurricanes", "Hurricanes"],
    "panthers": ["Florida Panthers", "Panthers"],
    "lightning": ["Tampa Bay Lightning", "Lightning"],
    "redwings": ["Detroit Red Wings", "Red Wings"],
    "bluejackets": ["Columbus Blue Jackets", "Blue Jackets"],
    "predators": ["Nashville Predators", "Predators"],
    "blackhawks": ["Chicago Blackhawks", "Blackhawks"],
    "blues": ["St. Louis Blues", "Blues"],
    "jets": ["Winnipeg Jets", "Jets"],
    "wild": ["Minnesota Wild", "Wild"],
    "avalanche": ["Colorado Avalanche", "Avalanche", "Avs"],
    "coyotes": ["Arizona Coyotes", "Coyotes"],
    "sharks": ["San Jose Sharks", "Sharks"],
    "ducks": ["Anaheim Ducks", "Ducks"],
    "kings": ["Los Angeles Kings", "Kings"],
    "flames": ["Calgary Flames", "Flames"],
    "oilers": ["Edmonton Oilers", "Oilers"],
    "senators": ["Ottawa Senators", "Senators"],
    "sabres": ["Buffalo Sabres", "Sabres"],
    "kraken": ["Seattle Kraken", "Kraken"],
    "goldenknights": ["Vegas Golden Knights", "Golden Knights"],
}


def _extract_team_slug(ticker: str) -> str | None:
    """Extract the team slug from a Kalshi sports ticker.

    E.g. KXNBA-26-CELTICS  -> 'celtics'
         KXNFL-SB60-CHIEFS  -> 'chiefs'
    """
    parts = ticker.split("-")
    if len(parts) >= 3:
        return parts[-1].lower()
    return None


def _team_matches(team_name: str, aliases: list[str]) -> bool:
    """Return True if any alias appears in team_name (case-insensitive)."""
    team_lower = team_name.lower()
    for alias in aliases:
        if alias.lower() in team_lower:
            return True
    return False


def _find_model_prob_for_team(slug: str, picks: list[dict]) -> float | None:
    """
    Given a team slug (e.g. 'celtics'), search through SportEdge picks
    for a matching team and return its model probability.
    """
    aliases = _TEAM_ALIASES.get(slug, [slug.title()])
    for pick in picks:
        home = pick.get("home_team", "")
        away = pick.get("away_team", "")
        selection = pick.get("selection", "")
        model_prob = pick.get("model_prob")

        if model_prob is None:
            continue

        if _team_matches(home, aliases) and selection == "home":
            return float(model_prob)
        if _team_matches(away, aliases) and selection == "away":
            return float(model_prob)

    return None


def compute_kalshi_edges(category: str = "", limit: int = 100) -> list[dict]:
    """
    Return Kalshi markets enriched with edge data where available.

    For sports markets:
      - Looks up matching SportEdge model probability
      - Computes edge = model_prob - kalshi_yes_price
      - Positive edge = model thinks outcome more likely than market

    For non-sports markets:
      - Returns market data with edge fields as None
    """
    markets = get_kalshi_markets(category=category, limit=limit)

    # Load SportEdge picks once (used for sports edge matching)
    try:
        picks = get_top_picks(limit=200, min_edge=0.0)
    except Exception as e:
        logger.warning(f"Could not load SportEdge picks for Kalshi edge calc: {e}")
        picks = []

    enriched = []
    for m in markets:
        m = dict(m)
        m["model_prob"] = None
        m["edge"] = None
        m["edge_label"] = None

        if m.get("category") == "Sports" and m.get("yes_price") is not None:
            slug = _extract_team_slug(m["ticker"])
            if slug:
                model_prob = _find_model_prob_for_team(slug, picks)
                if model_prob is not None:
                    yes_price = m["yes_price"]
                    edge = model_prob - yes_price
                    m["model_prob"] = model_prob
                    m["edge"] = edge
                    if edge > 0.05:
                        m["edge_label"] = "positive"
                    elif edge < -0.05:
                        m["edge_label"] = "negative"
                    else:
                        m["edge_label"] = "neutral"

        enriched.append(m)

    return enriched
