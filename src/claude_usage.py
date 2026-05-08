"""Claude-Code-Usage-Monitor — fragt internen OAuth-Endpoint ab.

Liest das OAuth-Token aus dem macOS-Keychain (Service "Claude Code-credentials")
und ruft https://api.anthropic.com/api/oauth/usage ab. Caching: 60 s.

Wichtig:
- Der Endpoint ist nicht offiziell dokumentiert. Wenn er bricht, liefert
  fetch_usage() ein Fehler-Dict mit "error"-Key — die UI zeigt dann eine Warnung.
- Wir senden einen ehrlichen User-Agent (audio-transkript/<version>) und den
  notwendigen Beta-Header.
"""

import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("AT")

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"
KEYCHAIN_SERVICE = "Claude Code-credentials"
CACHE_TTL = 60.0
APP_VERSION = "0.1.2"

_cache = {"ts": 0.0, "value": None}
_token_cache = {"ts": 0.0, "value": None}
_TOKEN_TTL = 30.0


def _read_token_from_keychain():
    """Liest OAuth-Token aus macOS-Keychain. Gibt None bei Fehler."""
    now = time.time()
    if _token_cache["value"] is not None and now - _token_cache["ts"] < _TOKEN_TTL:
        return _token_cache["value"]
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        raw = out.stdout.strip()
        if not raw:
            return None
        data = json.loads(raw)
        token = data.get("claudeAiOauth", {}).get("accessToken")
        if token:
            _token_cache["ts"] = now
            _token_cache["value"] = token
        return token
    except Exception as e:
        log.warning("Claude-Usage: Keychain-Lesen fehlgeschlagen: %s", e)
        return None


def _http_get(token):
    req = urllib.request.Request(USAGE_URL, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("anthropic-beta", BETA_HEADER)
    req.add_header("User-Agent", f"audio-transkript/{APP_VERSION}")
    req.add_header("Accept", "application/json")
    return urllib.request.urlopen(req, timeout=8)


def _parse_iso(ts):
    if not ts:
        return None
    try:
        # "2026-05-08T11:00:00Z" -> aware datetime in UTC
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None


def _normalize(raw):
    """Wandelt API-Response in flaches Dict mit allen relevanten Feldern."""
    def block(key):
        b = raw.get(key) or {}
        if not isinstance(b, dict):
            return {"pct": None, "reset": None}
        return {
            "pct": b.get("utilization"),
            "reset": _parse_iso(b.get("resets_at")),
        }

    extra_raw = raw.get("extra_usage") or {}
    if not isinstance(extra_raw, dict):
        extra_raw = {}

    return {
        "session": block("five_hour"),
        "week_all": block("seven_day"),
        "week_sonnet": block("seven_day_sonnet"),
        "week_opus": block("seven_day_opus"),
        "week_omelette": block("seven_day_omelette"),
        "extra": {
            "enabled": bool(extra_raw.get("is_enabled")),
            "monthly_limit": extra_raw.get("monthly_limit"),
            "used_credits": extra_raw.get("used_credits"),
            "pct": extra_raw.get("utilization"),
            "currency": extra_raw.get("currency"),
        },
    }


def fetch_usage(force=False):
    """Holt die aktuellen Usage-Daten.

    Returns:
        dict mit Schluesseln "ok": True und Daten, oder
        dict mit "ok": False und "error" + "detail".
    """
    now = time.time()
    if not force and _cache["value"] is not None and now - _cache["ts"] < CACHE_TTL:
        return _cache["value"]

    token = _read_token_from_keychain()
    if not token:
        result = {"ok": False, "error": "no_token",
                  "detail": "Kein Anmelde-Token gefunden — bitte `claude login` ausfuehren."}
        _cache["ts"] = now
        _cache["value"] = result
        return result

    def _try():
        try:
            with _http_get(token) as resp:
                body = resp.read().decode("utf-8")
                raw = json.loads(body)
                return {"ok": True, **_normalize(raw)}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"ok": False, "error": "unauthorized", "_retry": True,
                        "detail": "Anmeldung abgelaufen — bitte erneut bei Claude Code anmelden."}
            if e.code == 404:
                return {"ok": False, "error": "not_found",
                        "detail": "Endpoint hat sich geaendert — Pfad pruefen (/api/oauth/usage)."}
            if e.code == 429:
                return {"ok": False, "error": "rate_limit", "_extend_cache": True,
                        "detail": "Nutzungsdaten vorueber gehend nicht verfuegbar (Rate Limit) — wird spaeter wiederholt."}
            return {"ok": False, "error": "http", "detail": f"HTTP {e.code} von api.anthropic.com."}
        except urllib.error.URLError as e:
            return {"ok": False, "error": "network",
                    "detail": "Keine Verbindung zu api.anthropic.com."}
        except Exception as e:
            log.exception("Claude-Usage: unerwarteter Fehler: %s", e)
            return {"ok": False, "error": "unknown", "detail": str(e)}

    result = _try()

    # Bei 401 einmal Token aus Keychain neu lesen und retry
    if not result["ok"] and result.get("_retry"):
        _token_cache["value"] = None
        time.sleep(0.5)
        token = _read_token_from_keychain()
        if token:
            result = _try()

    if isinstance(result, dict):
        result.pop("_retry", None)
        extend = result.pop("_extend_cache", False)
    else:
        extend = False

    # Bei Rate-Limit: Cache 5 Minuten lang behalten statt 60 s
    cache_ts = now - CACHE_TTL + (300.0 if extend else CACHE_TTL)
    _cache["ts"] = cache_ts
    _cache["value"] = result
    return result


# --- Reset-Zeit-Formatierung (deutsch, Europe/Berlin) ---

_WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _berlin_zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Berlin")
    except Exception:
        return timezone.utc


def format_reset(dt_utc):
    """Formatiert UTC-datetime als deutsche Reset-Zeit."""
    if dt_utc is None:
        return "—"
    try:
        local = dt_utc.astimezone(_berlin_zone())
        now = datetime.now(_berlin_zone())
        today = now.date()
        target = local.date()
        hhmm = local.strftime("%H:%M")
        if target == today:
            return f"heute {hhmm} Uhr"
        days = (target - today).days
        if days == 1:
            return f"morgen {hhmm} Uhr"
        wd = _WD[local.weekday()]
        return f"{wd} {local.strftime('%d.%m.')} {hhmm} Uhr"
    except Exception:
        return "—"
