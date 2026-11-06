#!/usr/bin/env python3
"""Fork an exact native agent session into a tab of an existing Ghostty window."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import uuid

SCRIPT = Path(__file__).resolve().with_name("ghostty.applescript")


class ForkError(Exception):
    pass


def applescript(*args):
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(SCRIPT), *args],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ForkError(f"Ghostty automation unavailable: {exc}") from exc
    if result.returncode:
        raise ForkError("Ghostty automation failed. Check macOS Automation permission "
                        "and Ghostty AppleScript support. " + result.stderr.strip())
    return result.stdout.rstrip("\r\n")


def inventory():
    result = []
    for line in applescript("inventory").splitlines():
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise ForkError("Unexpected Ghostty inventory format")
        result.append(dict(zip(("window", "tab", "terminal", "tty"), fields)))
    return result


def process_ttys():
    """Use actual process ancestry, never inherited daemon terminal env vars."""
    found = set()
    pid = os.getpid()
    seen = set()
    for _ in range(64):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        try:
            result = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", "ppid=,tty="],
                capture_output=True, text=True, timeout=3,
            )
            fields = result.stdout.split()
            if result.returncode or len(fields) != 2:
                break
            pid = int(fields[0])
            if fields[1] not in ("??", "?"):
                found.add("/dev/" + fields[1].removeprefix("/dev/"))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            break
    return found


def select_window(rows, window, terminal, ttys):
    windows = {r["window"] for r in rows}
    if window:
        if window not in windows:
            raise ForkError("Requested Ghostty window not found; use --list")
        return window, "explicit-window"
    if terminal:
        matches = {r["window"] for r in rows if r["terminal"] == terminal}
        if len(matches) != 1:
            raise ForkError("Requested Ghostty terminal not found; use --list")
        return matches.pop(), "explicit-terminal"
    matches = {r["window"] for r in rows if r["tty"] in ttys}
    if len(matches) == 1:
        return matches.pop(), "process-tty"
    if len(windows) == 1:
        return windows.pop(), "only-window"
    if not windows:
        raise ForkError("No existing Ghostty window found")
    raise ForkError("Cannot identify the source among multiple Ghostty windows. "
                    "Use --list, then --window ID or --terminal ID. "
                    "Do not guess from the front window or a daemon environment.")


def session_id(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ForkError("An exact session UUID is required. For Codex, CODEX_THREAD_ID "
                        "is used if present. For Claude, pass --session from the skill's "
                        "CLAUDE_SESSION_ID substitution. No latest-session fallback.") from exc
    return str(parsed)


def launch_command(agent, session, cwd):
    executable = shutil.which(agent)
    if not executable:
        raise ForkError(f"{agent} executable not found in PATH")
    executable = str(Path(executable).absolute())
    args = ([executable, "fork", session, "--cd", str(cwd)] if agent == "codex"
            else [executable, "--resume", session, "--fork-session"])
    # A new UI process must not inherit the source agent's nested-session markers.
    command = ["/usr/bin/env", "-u", "CODEX_THREAD_ID", "-u", "CLAUDE_SESSION_ID",
               "-u", "CLAUDECODE"]
    # LaunchServices/Ghostty may have only the macOS system PATH. An absolute
    # codex.js path still uses /usr/bin/env node, so preserve runtime lookup too.
    command.append("PATH=" + os.environ.get("PATH", os.defpath))
    config_var = "CODEX_HOME" if agent == "codex" else "CLAUDE_CONFIG_DIR"
    if os.environ.get(config_var):
        command.append(f"{config_var}={os.environ[config_var]}")
    command.extend(args)
    # Ghostty executes this command in its shell; shlex quotes every argument.
    return shlex.join(command), args


def locate_created_tab(before, after, anchor):
    """Rebind to the source terminal after Ghostty changes the window identity."""
    windows = {r["window"] for r in after if r["terminal"] == anchor}
    old_tabs = {r["tab"] for r in before}
    candidates = [r for r in after if r["window"] in windows and r["tab"] not in old_tabs]
    if len(windows) == 1 and len(candidates) == 1:
        return candidates[0]
    return None


def create_tab(before, window, cwd, command, title, terminal=None):
    anchor = terminal or next(r["terminal"] for r in before if r["window"] == window)
    try:
        reply = applescript("open", anchor, str(cwd), command)
        if reply != "created":
            raise ForkError("Unexpected create-tab acknowledgement")
    except ForkError as exc:
        raise ForkError(f"Tab creation may have partially completed. Do not retry automatically; "
                        f"inspect --list first. {exc}") from exc
    # macOS may replace window-... with tab-group-...; a window ID comparison
    # cannot establish same-window placement. The source terminal remains stable.
    for attempt in range(20):
        try:
            created = locate_created_tab(before, inventory(), anchor)
        except ForkError as exc:
            raise ForkError(f"Creation acknowledged but inventory unavailable. "
                            f"Do not retry automatically; inspect Ghostty. {exc}") from exc
        if created:
            break
        time.sleep(0.1)
    else:
        raise ForkError("Creation acknowledged but new tab cannot be uniquely located "
                        "beside the source terminal. Do not retry automatically; inspect --list.")
    result = {"status": "tab-created", "window": created["window"],
              "tab": created["tab"], "terminal": created["terminal"],
              "source_terminal": anchor,
              "note": "Native agent startup/session loading is reported in the new tab."}
    try:
        applescript("decorate", created["terminal"], title)
    except ForkError as exc:
        # Cosmetic failure must not turn successful creation into a retry trigger.
        result["warning"] = f"Tab created; title/focus could not be updated: {exc}"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude"))
    parser.add_argument("--session", help="Exact source UUID (Codex: defaults to CODEX_THREAD_ID)")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--window", help="Explicit Ghostty window ID from --list")
    target.add_argument("--terminal", help="Explicit source Ghostty terminal UUID from --list")
    parser.add_argument("--list", action="store_true", help="List terminal/window IDs, without chat contents")
    parser.add_argument("--dry-run", action="store_true", help="Resolve command/window without creating a tab")
    args = parser.parse_args(argv)
    try:
        if sys.platform != "darwin":
            raise ForkError("This adapter requires macOS and Ghostty with AppleScript (verified: 1.4.0)")
        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
            raise ForkError("Remote SSH sessions are not supported by this local Ghostty adapter")
        if args.list:
            print(json.dumps(inventory(), indent=2))
            return 0
        agent = args.agent or ("codex" if os.environ.get("CODEX_THREAD_ID") else None)
        if not agent:
            raise ForkError("Specify --agent codex|claude and --session UUID")
        session = session_id(args.session or (os.environ.get("CODEX_THREAD_ID")
                                             if agent == "codex" else None))
        cwd = args.cwd.expanduser().resolve(strict=True)
        if not cwd.is_dir():
            raise ForkError("--cwd must be a directory")
        command, native_args = launch_command(agent, session, cwd)
        rows = inventory()
        window, source = select_window(rows, args.window, args.terminal, process_ttys())
        report = {"status": "planned", "agent": agent, "source_session": session,
                  "window": window, "window_selection": source, "cwd": str(cwd),
                  "argv": native_args}
        if not args.dry_run:
            report["source_window_before"] = window
            report.update(create_tab(rows, window, cwd, command,
                                     f"{agent} fork {session[:8]}", args.terminal))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ForkError, OSError) as exc:
        print(f"fork-tab: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
