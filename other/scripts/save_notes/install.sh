#!/bin/sh
set -eu

if [ "$(uname -s)" != Darwin ] || [ "$(id -u)" -eq 0 ]; then
    echo "Запустите установку из Терминала на Mac под своей учётной записью." >&2
    exit 1
fi
if ! /usr/bin/xcrun --find clang >/dev/null 2>&1 || ! /usr/bin/python3 --version >/dev/null 2>&1; then
    echo "Установите Command Line Tools командой xcode-select --install и повторите установку." >&2
    exit 1
fi

src=$(CDPATH='' cd "$(dirname "$0")" && pwd)
bin="$HOME/bin"
support="$HOME/Library/Application Support/save_notes"
agents="$HOME/Library/LaunchAgents"
label=local.save-notes
domain="gui/$(id -u)"
plist="$agents/$label.plist"

# Compile for this Mac and prepare the launch agent before replacing installed files.
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
/usr/bin/xcrun clang -fobjc-arc -fblocks -framework Foundation -framework CoreServices \
    "$src/watch_notes.m" -o "$stage/watch_notes"
/usr/bin/python3 - "$stage/agent.plist" "$label" "$support/watch_notes" "$HOME/notes" "$bin/save_notes" <<'PY'
import plistlib
import sys

output, label, watcher, notes, command = sys.argv[1:]
with open(output, "wb") as file:
    plistlib.dump({
        "Label": label,
        "ProgramArguments": [watcher, notes, command, str(6 * 60 * 60)],
        "KeepAlive": True,
        "ProcessType": "Background",
    }, file)
PY

mkdir -p "$agents" "$support" "$bin" "$HOME/notes"
/usr/bin/install -S -m 755 "$src/save_notes" "$bin/save_notes"
/usr/bin/install -S -m 755 "$stage/watch_notes" "$support/watch_notes"
/usr/bin/install -S -m 644 "$stage/agent.plist" "$plist"

if [ ! -f "$support/state.json" ]; then
    location=$(/usr/bin/defaults read com.apple.screencapture location 2>/dev/null || :)
    if [ -z "$location" ] || [ "$(dirname "$location")" != "$HOME/notes" ] || [ ! -d "$location" ]; then
        "$bin/save_notes" other
    fi
fi

if /bin/launchctl print "$domain/$label" >/dev/null 2>&1; then
    /bin/launchctl bootout "$domain/$label"
fi
/bin/launchctl bootstrap "$domain" "$plist"

case ":${PATH}:" in
    *":$bin:"*) ;;
    *)
        profile="${ZDOTDIR:-$HOME}/.zshrc"
        path_line='case ":$PATH:" in *":$HOME/bin:"*) ;; *) export PATH="$HOME/bin:$PATH" ;; esac'
        if ! grep -Fqx "$path_line" "$profile" 2>/dev/null; then
            printf '\n%s\n' "$path_line" >> "$profile"
        fi
        ;;
esac
printf '%s\n' 'Откройте новую вкладку Терминала и выполните save_notes или save_notes "имя папки".'
