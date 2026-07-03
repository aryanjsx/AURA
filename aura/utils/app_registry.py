# aura/utils/app_registry.py
# Maps natural-language app/site names to executable commands or URLs.
# ─────────────────────────────────────────────────────────────────────
# RULE: URL entries are plain strings starting with "https://".
#       App entries are the executable name string or a list of args.
#       NEVER put a browser name before a URL — use open_url() instead.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations
import platform
import logging
import re

logger = logging.getLogger("aura.app_registry")

_OS = platform.system().lower()   # "windows" | "linux" | "darwin"


# ─────────────────────────────────────────────────────────────────────
# WEBSITES — all entries are plain "https://..." strings.
# open_app() detects these as URLs and routes to open_url() automatically.
# The open_url() method uses Python's webbrowser module (OS default browser).
# ─────────────────────────────────────────────────────────────────────

_WEBSITES: dict[str, str] = {
    # Video / Streaming
    "youtube":          "https://www.youtube.com",
    "netflix":          "https://www.netflix.com",
    "twitch":           "https://www.twitch.tv",
    "prime video":      "https://www.primevideo.com",
    "hotstar":          "https://www.hotstar.com",
    "disney plus":      "https://www.disneyplus.com",
    "hulu":             "https://www.hulu.com",
    "vimeo":            "https://www.vimeo.com",

    # Social / Communication
    "twitter":          "https://www.twitter.com",
    "x":                "https://www.x.com",
    "instagram":        "https://www.instagram.com",
    "facebook":         "https://www.facebook.com",
    "linkedin":         "https://www.linkedin.com",
    "reddit":           "https://www.reddit.com",
    "whatsapp":         "https://web.whatsapp.com",
    "telegram":         "https://web.telegram.org",
    "pinterest":        "https://www.pinterest.com",
    "snapchat":         "https://web.snapchat.com",
    "tiktok":           "https://www.tiktok.com",

    # Developer tools
    "github":           "https://www.github.com",
    "gitlab":           "https://www.gitlab.com",
    "bitbucket":        "https://www.bitbucket.org",
    "stackoverflow":    "https://www.stackoverflow.com",
    "stack overflow":   "https://www.stackoverflow.com",
    "codepen":          "https://www.codepen.io",
    "replit":           "https://www.replit.com",
    "npm":              "https://www.npmjs.com",
    "pypi":             "https://www.pypi.org",
    "docker hub":       "https://hub.docker.com",
    "vercel":           "https://www.vercel.com",
    "netlify":          "https://www.netlify.com",
    "heroku":           "https://www.heroku.com",
    "cloudflare":       "https://www.cloudflare.com",
    "aws console":      "https://console.aws.amazon.com",
    "google cloud":     "https://console.cloud.google.com",
    "azure portal":     "https://portal.azure.com",

    # Documentation
    "mdn":              "https://developer.mozilla.org",
    "mdn docs":         "https://developer.mozilla.org",
    "python docs":      "https://docs.python.org",
    "fastapi docs":     "https://fastapi.tiangolo.com",
    "react docs":       "https://react.dev",
    "tailwind docs":    "https://tailwindcss.com/docs",
    "anthropic docs":   "https://docs.anthropic.com",

    # Productivity / Google Workspace
    "gmail":            "https://mail.google.com",
    "google drive":     "https://drive.google.com",
    "google docs":      "https://docs.google.com",
    "google sheets":    "https://sheets.google.com",
    "google slides":    "https://slides.google.com",
    "google calendar":  "https://calendar.google.com",
    "google meet":      "https://meet.google.com",
    "google maps":      "https://maps.google.com",
    "google translate": "https://translate.google.com",
    "maps":             "https://maps.google.com",

    # Search
    "google":           "https://www.google.com",
    "bing":             "https://www.bing.com",
    "duckduckgo":       "https://www.duckduckgo.com",
    "duck duck go":     "https://www.duckduckgo.com",

    # Shopping / Finance
    "amazon":           "https://www.amazon.com",
    "flipkart":         "https://www.flipkart.com",
    "ebay":             "https://www.ebay.com",
    "paypal":           "https://www.paypal.com",

    # News
    "hacker news":      "https://news.ycombinator.com",
    "hn":               "https://news.ycombinator.com",
    "bbc":              "https://www.bbc.com",
    "cnn":              "https://www.cnn.com",

    # Music
    "spotify":          "https://open.spotify.com",
    "soundcloud":       "https://www.soundcloud.com",
    "apple music":      "https://music.apple.com",

    # AI Tools
    "chatgpt":          "https://chat.openai.com",
    "claude":           "https://claude.ai",
    "gemini":           "https://gemini.google.com",
    "perplexity":       "https://www.perplexity.ai",
    "midjourney":       "https://www.midjourney.com",

    # Misc
    "wikipedia":        "https://www.wikipedia.org",
    "notion":           "https://www.notion.so",
    "trello":           "https://www.trello.com",
    "jira":             "https://www.atlassian.com/software/jira",
    "figma":            "https://www.figma.com",
    "canva":            "https://www.canva.com",
}

# ─────────────────────────────────────────────────────────────────────
# NATIVE APPS — executable names only.
# DO NOT put URLs here. DO NOT hardcode browser names before URLs.
# ─────────────────────────────────────────────────────────────────────

_WINDOWS_APPS: dict[str, str | list[str]] = {
    # Browsers (apps, not URLs)
    "chrome":               "chrome",
    "google chrome":        "chrome",
    "firefox":              "firefox",
    "edge":                 "msedge",
    "microsoft edge":       "msedge",
    "brave":                "brave",
    "opera":                "opera",

    # Dev tools
    "vscode":               "code",
    "vs code":              "code",
    "visual studio code":   "code",
    "visual studio":        "devenv",
    "notepad":              "notepad",
    "notepad++":            "notepad++",
    "terminal":             ["cmd", "/K"],
    "cmd":                  "cmd",
    "powershell":           "powershell",
    "git bash":             "git-bash",
    "wsl":                  "wsl",
    "postman":              "postman",

    # Communication (native apps)
    "discord":              "discord",
    "slack":                "slack",
    "teams":                "teams",
    "zoom":                 "zoom",

    # Media (native apps)
    "spotify":              "spotify",
    "vlc":                  "vlc",
    "media player":         "wmplayer",

    # Productivity
    "explorer":             "explorer",
    "file explorer":        "explorer",
    "calculator":           "calc",
    "task manager":         "taskmgr",
    "control panel":        "control",
    "paint":                "mspaint",
    "snipping tool":        "snippingtool",
    "word":                 "winword",
    "excel":                "excel",
    "powerpoint":           "powerpnt",
    "settings":             "ms-settings:",

    # System
    "device manager":       ["mmc", "devmgmt.msc"],
    "event viewer":         ["mmc", "eventvwr.msc"],
    "registry editor":      "regedit",
    "clock":                "ms-clock:",
    "store":                "ms-windows-store:",
}

_LINUX_APPS: dict[str, str | list[str]] = {
    "chrome":               "google-chrome",
    "google chrome":        "google-chrome",
    "firefox":              "firefox",
    "brave":                "brave-browser",
    "vscode":               "code",
    "vs code":              "code",
    "terminal":             "x-terminal-emulator",
    "discord":              "discord",
    "spotify":              "spotify",
    "vlc":                  "vlc",
    "files":                "nautilus",
    "calculator":           "gnome-calculator",
    "settings":             "gnome-control-center",
}

_MACOS_APPS: dict[str, str | list[str]] = {
    "chrome":               "Google Chrome",
    "safari":               "Safari",
    "firefox":              "Firefox",
    "vscode":               "Visual Studio Code",
    "vs code":              "Visual Studio Code",
    "terminal":             "Terminal",
    "finder":               "Finder",
    "discord":              "Discord",
    "spotify":              "Spotify",
    "vlc":                  "VLC",
}

# Select platform registry
_NATIVE_APPS: dict[str, str | list[str]] = {
    "windows": _WINDOWS_APPS,
    "linux":   _LINUX_APPS,
    "darwin":  _MACOS_APPS,
}.get(_OS, _WINDOWS_APPS)

# Merge websites + native apps (native apps override websites for ambiguous names
# like "spotify" so the native app is tried first)
_FULL_REGISTRY: dict[str, str | list[str]] = {**_WEBSITES, **_NATIVE_APPS}


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def get_command(app_name: str) -> str | list[str] | None:
    """
    Look up an app name or website alias.

    Returns:
        str       — executable name (e.g. "spotify") or URL ("https://...")
        list[str] — command with args (e.g. ["cmd", "/K"])
        None      — not found (caller should try guess_url() as fallback)
    """
    return _FULL_REGISTRY.get(app_name.strip().lower())


def guess_url(name: str) -> str | None:
    """
    Try to construct a plausible URL for an unlisted site name.
    Returns None if the name looks like a local app, not a website.

    Examples:
        guess_url("github")        -> "https://www.github.com"
        guess_url("trello")        -> "https://www.trello.com"
        guess_url("devenv")        -> None  (looks like a local app)
    """
    clean = name.strip().lower().replace(" ", "")

    if any(clean.endswith(ext) for ext in [".exe", ".app", ".bat", ".sh"]):
        return None
    if len(clean) <= 2:
        return None
    if not re.match(r"^[a-z0-9\-]+$", clean):
        return None

    return f"https://www.{clean}.com"


def is_url(value: str) -> bool:
    """
    Returns True if the value looks like a web URL.
    Handles http, https, and Windows ms- protocol links.
    """
    return value.startswith(("http://", "https://", "ms-"))


def list_all_websites() -> list[str]:
    """All registered website aliases — for help/debug output."""
    return sorted(_WEBSITES.keys())


def list_all_apps() -> list[str]:
    """All registered native app aliases — for help/debug output."""
    return sorted(_NATIVE_APPS.keys())
