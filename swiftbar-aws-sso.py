#!/usr/bin/env -S python3 -B
# <xbar.title>AWS SSO</xbar.title>
# <xbar.version>1.0.0</xbar.version>
# <xbar.author>Guillaume Hertault</xbar.author>
# <xbar.author.github>guihash</xbar.author.github>
# <xbar.desc>Cloud icon in the menu bar; STS check in background; OS notification when the session expires.</xbar.desc>
# <xbar.dependencies>python3,aws</xbar.dependencies>
# <swiftbar.schedule>* * * * *</swiftbar.schedule>
# <swiftbar.environment>[SWIFTBAR_AWS_PROFILE=, AWS=, ALERTER=]</swiftbar.environment>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
"""
AWS SSO Session Status for SwiftBar.

Rendering is instant: the menu always shows the last cached state (STATE_FILE).
The STS check runs in a background subprocess and refreshes SwiftBar only when
the auth state changes, so the menu bar never blocks on a network call.
"""

import configparser
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FALLBACK_DEFAULT_PROFILE = "default"

_PLUGIN_NAME    = "swiftbar-aws-sso"
CACHE_DIR       = Path(os.environ.get("SWIFTBAR_PLUGIN_CACHE_PATH",
                       Path.home() / "Library" / "Caches" / _PLUGIN_NAME))
STATE_FILE      = CACHE_DIR / "state"
LAST_CHECK_FILE = CACHE_DIR / "last-check"

LOG_FILE        = Path.home() / "Library" / "Logs" / _PLUGIN_NAME / "plugin.log"

AWS_CONFIG_PATH   = Path.home() / ".aws" / "config"

ICON_OK    = "person.badge.key"
ICON_KO    = "person.badge.minus"

STS_TIMEOUT_S    = 8.0
CHECK_INTERVAL_S = 55.0  # background check fires at most once per ~minute

ENTRY     = Path(__file__).resolve()
ICON_PATH = ENTRY.parent / ".swiftbar-aws-sso" / "icon.png"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(action: str, message: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a") as f:
            f.write(f"{ts} {action}: {message}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# AWS config helpers
# ---------------------------------------------------------------------------

def _read_aws_config():
    if not AWS_CONFIG_PATH.exists():
        return None
    cfg = configparser.ConfigParser()
    cfg.read(AWS_CONFIG_PATH)
    return cfg


def _profile_section(name: str) -> str:
    return "DEFAULT" if name == "default" else f"profile {name}"


def _resolve_start_url(config, section: str):
    if section not in config:
        return None
    sec = config[section]
    if "sso_start_url" in sec:
        return sec["sso_start_url"].strip()
    session = sec.get("sso_session", "").strip()
    if not session:
        return None
    sess_key = f"sso-session {session}"
    if sess_key not in config:
        return None
    return config[sess_key].get("sso_start_url", "").strip() or None


def get_all_sso_profiles():
    config = _read_aws_config()
    if not config:
        return []
    profiles = []
    for section in config.sections():
        if section == "DEFAULT":
            if _resolve_start_url(config, "DEFAULT"):
                profiles.append("default")
        elif section.startswith("profile "):
            if _resolve_start_url(config, section):
                profiles.append(section[len("profile "):])
    if "DEFAULT" in config and _resolve_start_url(config, "DEFAULT"):
        if "default" not in profiles:
            profiles.insert(0, "default")
    return profiles


def get_sso_session_name(profile: str):
    config = _read_aws_config()
    if not config:
        return None
    section = _profile_section(profile)
    if section not in config:
        return None
    return config[section].get("sso_session", "").strip() or None


def get_start_url(profile: str):
    config = _read_aws_config()
    if not config:
        return None
    return _resolve_start_url(config, _profile_section(profile))


# ---------------------------------------------------------------------------
# Profile preference
# ---------------------------------------------------------------------------

def get_default_profile() -> str:
    env = os.environ.get("SWIFTBAR_AWS_PROFILE", "").strip()
    if env:
        return env
    for p in get_all_sso_profiles():
        if p.strip():
            return p.strip()
    return FALLBACK_DEFAULT_PROFILE


def _profile_matching_default(config) -> str | None:
    """Find the [profile X] whose key/value pairs match [default]."""
    if "default" not in config:
        return None
    default_items = dict(config["default"])
    if not default_items:
        return None
    for section in config.sections():
        if not section.startswith("profile "):
            continue
        if dict(config[section]) == default_items:
            return section[len("profile "):]
    return None


def get_selected_profile() -> str:
    config = _read_aws_config()
    if config and "default" in config and dict(config["default"]):
        match = _profile_matching_default(config)
        if match:
            return match
        return "default"
    return get_default_profile() or FALLBACK_DEFAULT_PROFILE


def apply_default_profile(profile_name: str) -> bool:
    if profile_name == "default" or not AWS_CONFIG_PATH.exists():
        return False
    try:
        original = AWS_CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        return False

    backup = AWS_CONFIG_PATH.with_name("config.swiftbar.bak")
    if not backup.exists():
        try:
            backup.write_text(original, encoding="utf-8")
        except OSError:
            pass

    config = configparser.ConfigParser()
    try:
        config.read_string(original)
    except configparser.Error:
        return False
    section = f"profile {profile_name}"
    if section not in config:
        return False

    new_lines = [
        "[default]",
        "# managed by SwiftBar plugin (swiftbar-aws-sso) — edits here are overwritten on profile switch",
    ]
    for key, value in config[section].items():
        new_lines.append(f"{key} = {value}")
    new_block = "\n".join(new_lines) + "\n"

    lines = original.splitlines(keepends=True)
    out, i, n, replaced = [], 0, len(lines), False
    while i < n:
        stripped = lines[i].strip()
        if stripped == "[default]" and not replaced:
            replaced = True
            i += 1
            while i < n:
                s = lines[i].strip()
                if s.startswith("[") and s.endswith("]"):
                    break
                i += 1
            out.append(new_block)
            if i < n:
                out.append("\n")
            continue
        out.append(lines[i])
        i += 1

    if not replaced:
        out = [new_block, "\n"] + out

    try:
        AWS_CONFIG_PATH.write_text("".join(out), encoding="utf-8")
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

def _resolve_tool(env_name: str, name: str, *fallbacks: str):
    env_val = os.environ.get(env_name, "").strip()
    if env_val and os.path.isfile(env_val) and os.access(env_val, os.X_OK):
        return env_val
    which = shutil.which(name)
    if which:
        return which
    for p in fallbacks:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def resolve_aws_cli():
    return _resolve_tool("AWS", "aws", "/opt/homebrew/bin/aws", "/usr/local/bin/aws")


def resolve_alerter():
    return _resolve_tool("ALERTER", "alerter", "/opt/homebrew/bin/alerter", "/usr/local/bin/alerter")


def sts_works(profile: str) -> bool:
    aws = resolve_aws_cli()
    if not aws:
        return False
    try:
        r = subprocess.run(
            [aws, "sts", "get-caller-identity", "--profile", profile],
            capture_output=True,
            timeout=STS_TIMEOUT_S,
            check=False,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def read_state() -> str:
    if STATE_FILE.exists():
        try:
            return STATE_FILE.read_text().strip()
        except OSError:
            return ""
    return ""


def write_state(state: str):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(state)
    except OSError:
        pass


def _seconds_since_last_check() -> float:
    try:
        return time.time() - float(LAST_CHECK_FILE.read_text())
    except (OSError, ValueError):
        return float("inf")


def _mark_check_done():
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_CHECK_FILE.write_text(str(time.time()))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def _alerter_base_cmd(alerter: str, title: str, message: str, timeout: int) -> list:
    cmd = [alerter, "--title", title, "--message", message,
           "--sound", "Glass", "--group", "swiftbar-aws-sso", "--timeout", str(timeout)]
    if ICON_PATH.is_file():
        cmd += ["--app-icon", str(ICON_PATH)]
    return cmd


def _osascript(script: str, timeout: float = 5.0):
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        pass


def notify(title: str, message: str):
    """Best-effort fire-and-forget notification (alerter → osascript fallback)."""
    log("notify", f"{title} — {message}")
    alerter = resolve_alerter()
    if alerter:
        try:
            subprocess.Popen(
                _alerter_base_cmd(alerter, title, message, 30),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            return
        except OSError:
            pass
    safe_msg = message.replace('"', '\\"')
    safe_title = title.replace('"', '\\"')
    _osascript(f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"')


def alert(title: str, message: str):
    """Modal warning dialog — more visible than `notify` for unrecoverable errors."""
    log("alert", f"{title} — {message}")
    safe_msg = message.replace('"', '\\"')
    safe_title = title.replace('"', '\\"')
    _osascript(f'display alert "{safe_title}" message "{safe_msg}" as warning', timeout=30.0)


def _alerter_wait_for_action(title: str, message: str, action_label: str) -> bool:
    """Show the action notification and block until clicked / timed out / closed."""
    alerter = resolve_alerter()
    if not alerter:
        return False
    cmd = _alerter_base_cmd(alerter, title, message, 60) + ["--actions", action_label]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=70, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return (r.stdout or "").strip() == action_label


def notify_with_action(title: str, message: str, action_label: str, on_click_cmd: list):
    """
    Fire a notification with an action button. Returns immediately.
    If the user clicks the action, `on_click_cmd` runs detached.
    """
    args = [sys.executable, "-B", __file__, "--do-action",
            title, message, action_label] + [str(c) for c in on_click_cmd]
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        notify(title, message)


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

def do_login(sso_session: str, profile: str):
    aws = resolve_aws_cli()
    if not aws:
        alert("AWS SSO", "aws CLI not found. Install AWS CLI v2 or set AWS=/path/to/aws")
        return

    if not profile:
        profile = get_selected_profile()

    log("login", f"Checking STS for profile: {profile}")
    if sts_works(profile):
        _record_auth_state(True)
        notify("AWS SSO", "Already authenticated")
        return

    notify("AWS SSO", f"Opening browser to sign in for {profile}…")

    if sso_session:
        log("login", f"Running: aws sso login --sso-session {sso_session}")
        cmd = [aws, "sso", "login", "--sso-session", sso_session]
    else:
        log("login", f"Running: aws sso login --profile {profile}")
        cmd = [aws, "sso", "login", "--profile", profile]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        log("login", f"FAILED to invoke aws CLI: {e}")
        alert("AWS SSO", f"aws sso login could not run: {e}. See: {LOG_FILE}")
        return

    if r.returncode == 0:
        _record_auth_state(True)
        notify("AWS SSO", "Signed in")
    else:
        log("login", f"FAILED (exit {r.returncode}): {(r.stdout or '') + (r.stderr or '')}".strip())
        alert("AWS SSO", f"aws sso login failed (exit {r.returncode}). See: {LOG_FILE}")


def do_logout(profile: str):
    aws = resolve_aws_cli()
    if not aws:
        notify("AWS SSO", "aws CLI not found")
        return
    if not profile:
        profile = get_selected_profile()
    log("logout", f"Running: aws sso logout (profile {profile})")
    try:
        subprocess.run([aws, "sso", "logout"], capture_output=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, OSError):
        pass
    _record_auth_state(False)
    notify("AWS SSO", "Logged out")


# ---------------------------------------------------------------------------
# Background STS update
# ---------------------------------------------------------------------------

def _swiftbar_refresh():
    try:
        subprocess.run(
            ["open", f"swiftbar://refreshPlugin?name={ENTRY.name}"],
            capture_output=True, timeout=3, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _record_auth_state(authenticated: bool):
    """Pin the cached state to a fresh truth and refresh SwiftBar.
    Notification-triggered actions don't get SwiftBar's automatic refresh,
    so we always nudge the menu bar ourselves.
    """
    _mark_check_done()
    write_state("ok" if authenticated else "expired")
    _swiftbar_refresh()


def run_background_update():
    """Called as a subprocess: check STS, update state, notify + refresh if changed."""
    profile = get_selected_profile()
    _mark_check_done()
    is_authenticated = sts_works(profile)
    old_state = read_state()
    new_state = "ok" if is_authenticated else "expired"
    write_state(new_state)
    if old_state != new_state:
        log("state", f"{old_state or 'unknown'} → {new_state} (profile {profile})")
        _swiftbar_refresh()
    if old_state == "ok" and new_state == "expired":
        sso_session = get_sso_session_name(profile) or ""
        notify_with_action(
            "AWS SSO",
            f"Session expired for {profile}",
            "Renew",
            [str(ENTRY), "login", sso_session, profile],
        )


def _spawn_background_update():
    try:
        subprocess.Popen(
            [sys.executable, "-B", __file__, "--update"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_menu():
    profile = get_selected_profile()
    sso_session = get_sso_session_name(profile) or ""

    cached_state = read_state()
    if cached_state == "":
        # First launch: no cached state yet, do a synchronous check once.
        _mark_check_done()
        is_authenticated = sts_works(profile)
        write_state("ok" if is_authenticated else "expired")
    else:
        is_authenticated = cached_state == "ok"
        if _seconds_since_last_check() > CHECK_INTERVAL_S:
            _spawn_background_update()

    if is_authenticated:
        print(f" | sfimage={ICON_OK}")
    else:
        print(f" | sfimage={ICON_KO}")

    print("---")
    print(f"AWS SSO")
    print(f"Profile: {profile}")
    print(f"Status: {'active' if is_authenticated else 'not authenticated'}")

    profiles = get_all_sso_profiles()
    if len(profiles) > 1:
        print("---")
        print("Switch default profile")
        for p in profiles:
            mark = "✓ " if p == profile else ""
            print(f"--{mark}{p} | bash={ENTRY} param0=select-profile param1={p} terminal=false refresh=true")

    print("---")

    start_url = get_start_url(profile)
    if start_url:
        print(f"Open AWS Console | href={start_url}")

    if is_authenticated:
        print(f"Sign out | bash={ENTRY} param0=logout param1={profile} terminal=false refresh=true")
    else:
        print(f"Sign in | bash={ENTRY} param0=login param1={sso_session} param2={profile} terminal=false refresh=true")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "--update":
        run_background_update()
        return

    if cmd == "--do-action":
        title, message, action_label = sys.argv[2], sys.argv[3], sys.argv[4]
        on_click_cmd = sys.argv[5:]
        if _alerter_wait_for_action(title, message, action_label):
            try:
                subprocess.Popen(
                    on_click_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
            except OSError:
                pass
        return

    if cmd == "select-profile":
        if len(sys.argv) < 3:
            return
        new_profile = sys.argv[2]
        apply_default_profile(new_profile)
        is_authenticated = sts_works(new_profile)
        _record_auth_state(is_authenticated)
        if is_authenticated:
            notify("AWS SSO", f"Switched to {new_profile} — credentials OK")
        else:
            sso_session = get_sso_session_name(new_profile) or ""
            notify_with_action(
                "AWS SSO",
                f"Switched to {new_profile} — not authenticated",
                "Sign in",
                [str(ENTRY), "login", sso_session, new_profile],
            )
        return

    if cmd == "login":
        sso_session = sys.argv[2] if len(sys.argv) > 2 else ""
        profile     = sys.argv[3] if len(sys.argv) > 3 else ""
        do_login(sso_session, profile)
        return

    if cmd == "logout":
        profile = sys.argv[2] if len(sys.argv) > 2 else ""
        do_logout(profile)
        return

    render_menu()


if __name__ == "__main__":
    main()
