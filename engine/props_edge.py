import logging
import statistics
from collections import defaultdict
from config import config

logger = logging.getLogger("engine.props_edge")

# Books considered "sharp" (not DFS platforms)
SHARP_BOOKS = {
    "draftkings", "fanduel", "betmgm", "caesars", "pointsbet",
    "betrivers", "barstool", "wynnbet", "betonlineag", "bovada",
    "unibet_us", "twinspires", "betus", "mybookieag", "lowvig",
    "espnbet", "hardrockbet", "hardrockbet_az",
}

# DFS / social platforms — treated separately, NOT used for sharp consensus
DFS_BOOKS = {
    "prizepicks", "underdog_fantasy", "underdog",
    "betr_us_dfs", "fliff",
}


def find_prop_edges(
    props: list[dict],
    min_edge: float | None = None,
) -> list[dict]:
    """
    For each player+stat combination, collect lines across all books,
    compute consensus line (median of sharp books), and find edges.

    Edge definition:
      - OVER edge: best_line > consensus_line (book offers a higher line to go over —
        actually harder but the discrepancy vs DFS is the value)
      - For cross-book comparison: we want books offering a LOWER line for overs
        (easier to beat) or a HIGHER line for unders (easier to beat).

    The main value detection pattern for props:
      - Consensus = median of all book lines
      - If a book's line is LOWER than consensus -> OVER opportunity (easier to hit)
      - If a book's line is HIGHER than consensus -> UNDER opportunity (easier to hit)
      - Special: compare PrizePicks/Underdog line vs sharp consensus
    """
    if min_edge is None:
        min_edge = getattr(config, "props", None)
        min_edge = min_edge.min_edge if min_edge else 0.05

    # Group by player + stat_type
    # Key: (player_name, stat_type)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in props:
        key = (p["player_name"], p["stat_type"])
        groups[key].append(p)

    picks = []
    for (player_name, stat_type), book_lines in groups.items():
        if len(book_lines) < 2:
            # Need at least 2 books to find an edge
            continue

        # Separate sharp lines from DFS lines
        sharp_lines = [b for b in book_lines if b["bookmaker"] in SHARP_BOOKS]
        dfs_lines = [b for b in book_lines if b["bookmaker"] in DFS_BOOKS]
        all_lines = [b for b in book_lines if b["line"] is not None]

        if not all_lines:
            continue

        line_values = [b["line"] for b in all_lines]
        consensus_line = statistics.median(line_values)

        # Pull PrizePicks line if available
        pp_entry = next(
            (b for b in dfs_lines if b["bookmaker"] == "prizepicks"), None
        )
        pp_line = pp_entry["line"] if pp_entry else None

        # Find best OVER opportunity: book with the LOWEST line (easiest to go over)
        over_candidates = [b for b in all_lines]
        over_candidates.sort(key=lambda b: b["line"])
        best_over = over_candidates[0] if over_candidates else None

        # Find best UNDER opportunity: book with the HIGHEST line (easiest to go under)
        under_candidates = sorted(all_lines, key=lambda b: b["line"], reverse=True)
        best_under = under_candidates[0] if under_candidates else None

        # Calculate edge for OVER: (consensus - best_line) / consensus
        # Positive means the book's line is lower than consensus -> value on over
        if best_over and consensus_line > 0:
            over_edge = (consensus_line - best_over["line"]) / consensus_line
        else:
            over_edge = 0.0

        # Calculate edge for UNDER: (best_line - consensus) / consensus
        # Positive means the book's line is higher than consensus -> value on under
        if best_under and consensus_line > 0:
            under_edge = (best_under["line"] - consensus_line) / consensus_line
        else:
            under_edge = 0.0

        # Special: PrizePicks vs sharp consensus edge
        # If PP line is significantly lower than sharp consensus -> OVER on PP
        # If PP line is significantly higher than sharp consensus -> UNDER on PP
        if pp_line is not None and sharp_lines and consensus_line > 0:
            sharp_vals = [b["line"] for b in sharp_lines]
            sharp_consensus = statistics.median(sharp_vals)
            pp_over_edge = (sharp_consensus - pp_line) / sharp_consensus if sharp_consensus > 0 else 0
            pp_under_edge = (pp_line - sharp_consensus) / sharp_consensus if sharp_consensus > 0 else 0
        else:
            pp_over_edge = 0.0
            pp_under_edge = 0.0
            sharp_consensus = consensus_line

        # Determine if we have a qualifying pick
        # Use the first sample's game_id/sport (same for all in group)
        sample = all_lines[0]
        game_id = sample.get("game_id")
        sport = sample.get("sport", "")

        # Check general cross-book OVER edge
        if over_edge >= min_edge and best_over:
            picks.append({
                "game_id": game_id,
                "sport": sport,
                "player_name": player_name,
                "stat_type": stat_type,
                "direction": "OVER",
                "consensus_line": round(consensus_line, 1),
                "best_line": best_over["line"],
                "best_book": best_over["bookmaker"],
                "edge_pct": round(over_edge, 4),
                "pp_line": pp_line,
                "num_books": len(all_lines),
            })

        # Check general cross-book UNDER edge
        if under_edge >= min_edge and best_under:
            picks.append({
                "game_id": game_id,
                "sport": sport,
                "player_name": player_name,
                "stat_type": stat_type,
                "direction": "UNDER",
                "consensus_line": round(consensus_line, 1),
                "best_line": best_under["line"],
                "best_book": best_under["bookmaker"],
                "edge_pct": round(under_edge, 4),
                "pp_line": pp_line,
                "num_books": len(all_lines),
            })

        # Check PrizePicks-specific edges (separate picks if above threshold)
        if pp_over_edge >= min_edge and pp_line is not None:
            # Only add PP pick if it's not already covered by general over pick
            if not any(
                p["player_name"] == player_name
                and p["stat_type"] == stat_type
                and p["direction"] == "OVER"
                and p["best_book"] == "prizepicks"
                for p in picks
            ):
                picks.append({
                    "game_id": game_id,
                    "sport": sport,
                    "player_name": player_name,
                    "stat_type": stat_type,
                    "direction": "OVER",
                    "consensus_line": round(sharp_consensus, 1),
                    "best_line": pp_line,
                    "best_book": "prizepicks",
                    "edge_pct": round(pp_over_edge, 4),
                    "pp_line": pp_line,
                    "num_books": len(all_lines),
                })

        if pp_under_edge >= min_edge and pp_line is not None:
            if not any(
                p["player_name"] == player_name
                and p["stat_type"] == stat_type
                and p["direction"] == "UNDER"
                and p["best_book"] == "prizepicks"
                for p in picks
            ):
                picks.append({
                    "game_id": game_id,
                    "sport": sport,
                    "player_name": player_name,
                    "stat_type": stat_type,
                    "direction": "UNDER",
                    "consensus_line": round(sharp_consensus, 1),
                    "best_line": pp_line,
                    "best_book": "prizepicks",
                    "edge_pct": round(pp_under_edge, 4),
                    "pp_line": pp_line,
                    "num_books": len(all_lines),
                })

    # Sort by edge descending
    picks.sort(key=lambda x: x["edge_pct"], reverse=True)
    logger.info(
        f"Props edge finder: {len(picks)} picks found from "
        f"{len(groups)} player+stat combos"
    )
    return picks
