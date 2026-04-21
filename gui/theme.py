# Design system matching the HTML prototype

BG_PANEL   = "#14181e"
BG_ELEV    = "#191d24"
BG_INPUT   = "#0c0f13"
BG_ROW     = "#161a20"
BD_SUBTLE  = "#22272f"
BD         = "#2a303a"
BD_STRONG  = "#363d48"
BD_FOCUS   = "#3c8fe0"

FG         = "#dde2e9"
FG_MUTED   = "#9aa3ae"
FG_DIM     = "#6b7380"
FG_FAINT   = "#4b525d"

ACCENT     = "#3c8fe0"
ACCENT_HI  = "#4ea3f5"
OK         = "#5abf7a"
WARN       = "#d4a957"
ERR        = "#e06060"
INFO       = "#4a9eff"

MONO    = "JetBrains Mono"
UI      = "Inter"

BADGE_STYLES = {
    "Downloading": (INFO,    "#0e1f38", "#163258"),
    "Recording":   (ERR,     "#2b1212", "#4a2020"),
    "Scheduled":   (WARN,    "#2b2210", "#4a3a18"),
    "Done":        (OK,      "#0f2418", "#1a3e28"),
    "Failed":      (ERR,     "#2b1212", "#4a2020"),
    "Cancelled":   (FG_DIM,  "#181c22", "#2a303a"),
    "Running":     (INFO,    "#0e1f38", "#163258"),
    "Starting":    (FG_MUTED,"#181c22", "#262c36"),
    "Starting…":   (FG_MUTED,"#181c22", "#262c36"),
    "Trimming…":   (WARN,    "#2b2210", "#4a3a18"),
    "Error":       (ERR,     "#2b1212", "#4a2020"),
}

def badge_colors(status: str):
    """Return (text_color, bg, border) for a status string."""
    key = status.split("(")[0].strip().rstrip("…").strip()
    return BADGE_STYLES.get(key, (FG_MUTED, "#181c22", "#262c36"))
