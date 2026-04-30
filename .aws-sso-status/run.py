#!/usr/bin/env -S python3 -B
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.version>3.2.0</swiftbar.version>
# <swiftbar.title>AWS SSO Status</swiftbar.title>
# <swiftbar.author>guihash</swiftbar.author>
# <swiftbar.desc>Cloud icon in the menu bar; STS check every minute; OS notification when the session expires.</swiftbar.desc>
# Do not chmod +x — SwiftBar lists every executable in the plugin folder as a menu plugin.
"""
AWS SSO Session Status for SwiftBar.

The script is invoked by aws-sso-status.1m.sh every minute. It calls
`aws sts get-caller-identity` to detect whether the active SSO session is
still valid, draws the menu bar item (cloud icon, green/red), and emits a
macOS notification when the session expires or after a profile switch.
"""

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Used only when ~/.aws/config has zero SSO profiles. Override with the
# SWIFTBAR_AWS_PROFILE env var for a per-machine default.
FALLBACK_DEFAULT_PROFILE = "default"

PROFILE_PREF_FILE = Path.home() / ".aws" / "swiftbar-profile"
STATE_FILE = Path.home() / ".aws" / "swiftbar-sso-state"
SWITCH_MARKER = Path.home() / ".aws" / "swiftbar-sso-just-switched"
AWS_CONFIG_PATH = Path.home() / ".aws" / "config"

ICON_OK = "cloud.fill"
ICON_KO = "xmark.icloud.fill"
COLOR_OK = "#7ED321,#7ED321"
COLOR_KO = "#FF3B30,#FF6B5E"

STS_TIMEOUT_S = 8.0


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
ENTRY = _swiftbar_entry()


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


def get_selected_profile() -> str:
    if PROFILE_PREF_FILE.exists():
        try:
            text = PROFILE_PREF_FILE.read_text().strip()
            if text:
                return text
        except OSError:
            pass
    return get_default_profile() or FALLBACK_DEFAULT_PROFILE


def set_selected_profile(name: str):
    PROFILE_PREF_FILE.write_text(name)


def apply_default_profile(profile_name: str) -> bool:
    """
    Replace the [default] block in ~/.aws/config with the contents of
    [profile <profile_name>]. Preserves other profile blocks and comments.
    Backs up the original once on first change to ~/.aws/config.swiftbar.bak.
    No-op if profile_name == "default" or the source profile cannot be found.
    """
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
    """True if `aws sts get-caller-identity` succeeds for this profile."""
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
# State transitions and notifications
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


def notify(title: str, message: str):
    """Best-effort notification (alerter → osascript fallback)."""
    alerter = resolve_alerter()
    if alerter:
        try:
            icon = str(Path(__file__).resolve().parent / "icon.png")
            cmd = [alerter, "--title", title, "--message", message,
                   "--sound", "Glass", "--group", "aws-sso-status", "--timeout", "30"]
            if os.path.isfile(icon):
                cmd += ["--app-icon", icon]
            subprocess.Popen(
                cmd,
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


def handle_transition(profile: str, is_authenticated: bool):
    """Notify only on transition ok → expired (not on first run, not on manual logout)."""
    new_state = "ok" if is_authenticated else "expired"
    old_state = read_state()
    if old_state == "ok" and new_state == "expired":
        notify("AWS SSO", f"Session expired for {profile}")
    write_state(new_state)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "select-profile":
        if len(sys.argv) > 2:
            new_profile = sys.argv[2]
            set_selected_profile(new_profile)
            apply_default_profile(new_profile)
            try:
                STATE_FILE.unlink()
            except (OSError, FileNotFoundError):
                pass
            try:
                SWITCH_MARKER.write_text(new_profile)
            except OSError:
                pass
        sys.exit(0)

    profile = get_selected_profile()
    sso_session = get_sso_session_name(profile) or ""
    sso_sh = HELPERS / "sso.sh"

    is_authenticated = sts_works(profile)
    handle_transition(profile, is_authenticated)

    # Post-switch confirmation notification (only on the tick that follows a profile switch)
    if SWITCH_MARKER.exists():
        try:
            switched_to = SWITCH_MARKER.read_text().strip() or profile
            SWITCH_MARKER.unlink()
        except OSError:
            switched_to = profile
        if is_authenticated:
            notify("AWS SSO", f"Switched to {switched_to} — credentials OK")
        else:
            notify("AWS SSO", f"Switched to {switched_to} — not authenticated, click Sign in")

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
