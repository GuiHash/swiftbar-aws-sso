#!/usr/bin/env -S python3 -B
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.version>3.3.0</swiftbar.version>
# <swiftbar.title>AWS SSO Status</swiftbar.title>
# <swiftbar.author>guihash</swiftbar.author>
# <swiftbar.desc>Cloud icon in the menu bar; STS check in background; OS notification when the session expires.</swiftbar.desc>
# Do not chmod +x — SwiftBar lists every executable in the plugin folder as a menu plugin.
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
from pathlib import Path

FALLBACK_DEFAULT_PROFILE = "default"

STATE_FILE        = Path.home() / ".aws" / "swiftbar-sso-state"
LAST_CHECK_FILE   = Path.home() / ".aws" / "swiftbar-sso-last-check"
AWS_CONFIG_PATH   = Path.home() / ".aws" / "config"

ICON_OK  = "cloud.fill"
ICON_KO  = "xmark.icloud.fill"
COLOR_OK = "#7ED321,#7ED321"
COLOR_KO = "#FF3B30,#FF6B5E"

STS_TIMEOUT_S   = 8.0
CHECK_INTERVAL_S = 55.0  # background check fires at most once per ~minute


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _helpers_dir() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "sso.sh").is_file():
        return here
    return here.parent


def _swiftbar_entry() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "aws-sso-status.1m.sh"


HELPERS = _helpers_dir()
ENTRY   = _swiftbar_entry()


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
        "# managed by SwiftBar plugin (aws-sso-status) — edits here are overwritten on profile switch",
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
# AWS / STS check
# ---------------------------------------------------------------------------

def resolve_aws_cli():
    env_aws = os.environ.get("AWS", "").strip()
    if env_aws and os.path.isfile(env_aws) and os.access(env_aws, os.X_OK):
        return env_aws
    which = shutil.which("aws")
    if which:
        return which
    for p in ("/opt/homebrew/bin/aws", "/usr/local/bin/aws"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


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
        LAST_CHECK_FILE.write_text(str(time.time()))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def resolve_alerter():
    env_val = os.environ.get("ALERTER", "").strip()
    if env_val and os.path.isfile(env_val) and os.access(env_val, os.X_OK):
        return env_val
    which = shutil.which("alerter")
    if which:
        return which
    for p in ("/opt/homebrew/bin/alerter", "/usr/local/bin/alerter"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _alerter_base_cmd(alerter: str, title: str, message: str, timeout: int) -> list:
    icon = str(Path(__file__).resolve().parent / "icon.png")
    cmd = [alerter, "--title", title, "--message", message,
           "--sound", "Glass", "--group", "aws-sso-status", "--timeout", str(timeout)]
    if os.path.isfile(icon):
        cmd += ["--app-icon", icon]
    return cmd


def notify(title: str, message: str):
    """Best-effort fire-and-forget notification (alerter → osascript fallback)."""
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
    script = f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5, check=False)
    except (subprocess.TimeoutExpired, OSError):
        pass


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


def run_background_update():
    """Called as a subprocess: check STS, update state, notify + refresh if changed."""
    profile = get_selected_profile()
    _mark_check_done()
    is_authenticated = sts_works(profile)
    old_state = read_state()
    new_state = "ok" if is_authenticated else "expired"
    write_state(new_state)
    if old_state != new_state:
        _swiftbar_refresh()
    if old_state == "ok" and new_state == "expired":
        sso_session = get_sso_session_name(profile) or ""
        sso_sh = str(HELPERS / "sso.sh")
        notify_with_action(
            "AWS SSO",
            f"Session expired for {profile}",
            "Renew",
            [sso_sh, "login", sso_session, profile],
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

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--update":
        run_background_update()
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--do-action":
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
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--get-profile":
        print(get_selected_profile())
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "select-profile":
        if len(sys.argv) > 2:
            new_profile = sys.argv[2]
            apply_default_profile(new_profile)
            _mark_check_done()
            is_authenticated = sts_works(new_profile)
            write_state("ok" if is_authenticated else "expired")
            if is_authenticated:
                notify("AWS SSO", f"Switched to {new_profile} — credentials OK")
            else:
                sso_session = get_sso_session_name(new_profile) or ""
                sso_sh = str(HELPERS / "sso.sh")
                notify_with_action(
                    "AWS SSO",
                    f"Switched to {new_profile} — not authenticated",
                    "Sign in",
                    [sso_sh, "login", sso_session, new_profile],
                )
        sys.exit(0)

    profile = get_selected_profile()
    sso_session = get_sso_session_name(profile) or ""
    sso_sh = HELPERS / "sso.sh"

    # Render immediately from cached state — no network call here.
    cached_state = read_state()
    if cached_state == "":
        # First launch: no cached state yet, do a synchronous check once.
        _mark_check_done()
        is_authenticated = sts_works(profile)
        write_state("ok" if is_authenticated else "expired")
    else:
        is_authenticated = cached_state == "ok"
        # Kick off a background STS check if the last one is stale.
        if _seconds_since_last_check() > CHECK_INTERVAL_S:
            _spawn_background_update()

    if is_authenticated:
        print(f" | sfimage={ICON_OK} sfcolor={COLOR_OK}")
    else:
        print(f" | sfimage={ICON_KO} sfcolor={COLOR_KO}")

    print("---")
    print(f"Profile: {profile}")
    print(f"Status: {'active' if is_authenticated else 'not authenticated'}")
    print("---")

    if is_authenticated:
        print(f"Sign out | bash={sso_sh} param0=logout param1={profile} terminal=false refresh=true")
    else:
        print(f"Sign in | bash={sso_sh} param0=login param1={sso_session} param2={profile} terminal=false refresh=true")

    start_url = get_start_url(profile)
    if start_url:
        print(f"Open AWS Console | href={start_url}")

    profiles = get_all_sso_profiles()
    if len(profiles) > 1:
        print("---")
        print("Switch default profile")
        for p in profiles:
            mark = "✓ " if p == profile else ""
            print(f"--{mark}{p} | bash={ENTRY} param0=select-profile param1={p} terminal=false refresh=true")


if __name__ == "__main__":
    main()
