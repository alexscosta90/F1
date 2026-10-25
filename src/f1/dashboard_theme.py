"""Reusable visual tokens for the F1 dashboard."""

BACKGROUND = "#0E1117"
SURFACE = "#161B22"
TEXT = "#F5F7FA"
MUTED_TEXT = "#B0B8C4"
BORDER = "#30363D"
GRID = "#242B35"

TEAM_COLORS = {
    "Ferrari": "#DC0000",
    "Mercedes": "#00D2BE",
    "Red Bull Racing": "#0600EF",
    "Red Bull": "#0600EF",
    "McLaren": "#FF8700",
    "Alpine": "#0093CC",
    "Aston Martin": "#006F62",
    "Haas F1 Team": "#B6BABD",
    "Kick Sauber": "#52E252",
    "Sauber": "#52E252",
    "RB": "#6692FF",
    "Racing Bulls": "#6692FF",
    "Williams": "#64C4FF",
}

CHART_COLORS = list(dict.fromkeys(TEAM_COLORS.values()))
