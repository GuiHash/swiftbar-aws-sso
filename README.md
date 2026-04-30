# SwiftBar AWS SSO Status

A minimalist [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin that shows the status of your AWS SSO (IAM Identity Center) session in the macOS menu bar.

- Cloud icon — green when credentials are valid, red when expired.
- Click to **Sign in** (smart: only opens the browser if `aws sts get-caller-identity` fails) or **Sign out**.
- Optional **Switch default profile** menu when `~/.aws/config` declares several SSO profiles.
- Native macOS notifications when the session expires or after a profile switch.
- No daemon, no background process — just SwiftBar's 1-minute tick.

## Requirements

- macOS with [SwiftBar](https://github.com/swiftbar/SwiftBar) (`brew install --cask swiftbar`)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) (`brew install awscli`)
- Python 3 (ships with macOS Command Line Tools)
- An `~/.aws/config` already configured with one or more SSO profiles (see [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html))

## Install

```bash
git clone https://github.com/<your-user>/swiftbar-aws-sso-status.git
cd swiftbar-aws-sso-status
./install.sh
```

The installer will ask for:

1. The SwiftBar plugins directory (auto-detected from `defaults read com.ameba.SwiftBar PluginDirectory`).
2. The install mode:
   - **symlink** *(recommended)* — creates a symlink in the plugins folder. `git pull` updates the live plugin instantly.
   - **copy** — copies a snapshot to the plugins folder; the repo and the live plugin diverge.

Non-interactive examples:

```bash
./install.sh --symlink --yes                            # accept defaults
./install.sh --copy --plugins-dir ~/.swiftbar-plugins   # explicit snapshot install
```

After installation, open SwiftBar (`open -a SwiftBar`) and trigger **Refresh all** — the cloud icon should appear within a minute.

## Uninstall

```bash
./uninstall.sh           # remove plugin only, keep state files
./uninstall.sh --purge   # also delete state files in ~/.aws/
```

## How it works

Every minute, SwiftBar runs `aws-sso-status.1m.sh`, which delegates to `.aws-sso-status/run.py`. The script:

1. Resolves the active profile (env var `SWIFTBAR_AWS_PROFILE` → `~/.aws/swiftbar-profile` → first SSO profile in `~/.aws/config`).
2. Calls `aws sts get-caller-identity --profile <profile>` (8s timeout).
3. Renders the menu bar icon (`cloud.fill` green or `xmark.icloud.fill` red).
4. Compares the new state with the previous tick (`~/.aws/swiftbar-sso-state`) and fires a notification on `ok → expired`.

### Login flow

Clicking **Sign in** runs `.aws-sso-status/login.sh`, which:

1. Re-checks `aws sts get-caller-identity` — if already valid, it just notifies and exits.
2. Otherwise runs `aws sso login --sso-session <session>` (preferred) or `aws sso login --profile <profile>` and opens the system browser.
3. Logs everything to `~/.aws/swiftbar-sso-login.log` and surfaces a macOS notification on success/failure.

### Profile switching

Selecting a profile from the **Switch default profile** submenu does two things:

1. Saves the choice to `~/.aws/swiftbar-profile` (used by the plugin on every tick).
2. **Rewrites the `[default]` block in `~/.aws/config`** with the contents of `[profile <selected>]`, so any `aws ...` command without `--profile` uses the selected profile too.

The first time the file is rewritten, `~/.aws/config.swiftbar.bak` is created as a safety backup. After the next tick, an `STS check` confirms the new profile and a notification is fired.

## Files written outside the repo

| Path | Purpose |
| --- | --- |
| `~/.aws/swiftbar-profile` | Persists the active profile across reboots |
| `~/.aws/swiftbar-sso-state` | `ok` / `expired` from the last tick (used to detect transitions) |
| `~/.aws/swiftbar-sso-just-switched` | Marker dropped during a profile switch; consumed by the next tick |
| `~/.aws/swiftbar-sso-login.log` | Append-only log from `login.sh` / `logout.sh` |
| `~/.aws/config.swiftbar.bak` | One-shot backup of `~/.aws/config` before the first profile-switch rewrite |

## Configuration

| Env var | Effect |
| --- | --- |
| `SWIFTBAR_AWS_PROFILE` | Override the default profile if `~/.aws/swiftbar-profile` doesn't exist yet |
| `AWS` | Absolute path to the `aws` binary (used when it's not on `PATH`) |

## Troubleshooting

- **Menu bar shows red cloud right after `aws sso login`** — give it 60 seconds (next tick) or hit **Refresh all** in SwiftBar.
- **`aws sso login` browser tab doesn't auto-close** — that's standard AWS CLI behavior. Closing the tab manually is fine; the plugin will detect the new session on the next tick.
- **Multiple plugins appearing for `__pycache__`** — make sure the plugins folder has `.aws-sso-status/`, `__pycache__/`, `*.pyc` listed in its `.swiftbarignore` (the installer adds them automatically).
- **No SSO profile detected** — verify `~/.aws/config` has either `sso_start_url` or a `sso_session = <name>` referencing a `[sso-session <name>]` block.

## License

[MIT](LICENSE)
