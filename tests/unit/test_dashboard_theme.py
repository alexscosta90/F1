import tomllib
from pathlib import Path

from f1.dashboard_theme import (
    BACKGROUND,
    CHART_COLORS,
    SURFACE,
    TEAM_COLORS,
    TEXT,
)


def test_dashboard_theme_covers_local_teams_and_matches_streamlit_palette() -> None:
    root = Path(__file__).parents[2]
    with (root / ".streamlit" / "config.toml").open("rb") as config_file:
        streamlit_theme = tomllib.load(config_file)["theme"]

    local_teams = {
        "Alpine",
        "Aston Martin",
        "Ferrari",
        "Haas F1 Team",
        "Kick Sauber",
        "McLaren",
        "Mercedes",
        "RB",
        "Red Bull Racing",
        "Williams",
    }

    assert local_teams <= TEAM_COLORS.keys()
    assert streamlit_theme["backgroundColor"] == BACKGROUND == "#0E1117"
    assert streamlit_theme["secondaryBackgroundColor"] == SURFACE == "#161B22"
    assert streamlit_theme["textColor"] == TEXT == "#F5F7FA"
    assert streamlit_theme["chartCategoricalColors"] == CHART_COLORS
    assert TEAM_COLORS["Ferrari"] == "#DC0000"
    assert TEAM_COLORS["Mercedes"] == "#00D2BE"
    assert TEAM_COLORS["Red Bull Racing"] == "#0600EF"
    assert TEAM_COLORS["McLaren"] == "#FF8700"
