#!/usr/bin/env bash
# Optional: build the Apple-style icon font from YOUR OWN copy of Apple's SF Symbols.
#
#   tools/build-symbols-font.sh ~/Downloads/SF-Symbols-6.dmg [shell dir]
#
# SF Symbols is licensed by Apple for use in apps and design work for Apple platforms; the font
# cannot be redistributed, so this repository does not include it. The script extracts the
# symbol font from the disk image you downloaded from developer.apple.com and keeps only the
# nine glyphs the widget uses. You are responsible for complying with Apple's SF Symbols
# license. Without this font the widget uses Material Symbols icons.
# Needs: 7z (p7zip), cpio, gzip, python3 (fonttools is installed into a temporary venv if missing).
set -euo pipefail
dmg=${1:?usage: build-symbols-font.sh SF-Symbols.dmg [shell dir]}
shell=${2:-$HOME/.config/quickshell/caelestia}
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
cd "$work"
7z x -y "$dmg" >/dev/null
img=$(find . -name '*.hfs' -o -name '*.apfs' | head -1)
[ -n "$img" ] && 7z x -y "$img" >/dev/null
pkg=$(find . -name '*.pkg' | head -1)
[ -n "$pkg" ] || { echo "no .pkg found in the disk image" >&2; exit 1; }
7z x -y "$pkg" >/dev/null
for payload in $(find . -name 'Payload*'); do
    (mkdir -p "out_$(basename "$payload")" && cd "out_$(basename "$payload")" && { gzip -dc "../$payload" 2>/dev/null || cat "../$payload"; } | cpio -idm --quiet 2>/dev/null) || true
done
font=$(find . -name 'SFSymbolsFallback.otf' | head -1)
[ -n "$font" ] || { echo "SFSymbolsFallback.otf not found" >&2; exit 1; }
mkdir -p "$shell/assets/fonts"
if ! command -v pyftsubset >/dev/null; then
    python3 -m venv "$work/venv" && "$work/venv/bin/pip" install --quiet fonttools
    export PATH="$work/venv/bin:$PATH"
fi
# airpodpro.right/left, charging case, keyboard, game controller, mouse, headphones, phone, watch
pyftsubset "$font" --unicodes=U+100C8D,U+100C8E,U+100E6B,U+100E91,U+1006F9,U+100EB1,U+100EB9,U+100E90,U+100E97 \
    --output-file="$shell/assets/fonts/devices.otf" --no-layout-closure
echo "Wrote $shell/assets/fonts/devices.otf (personal use only, do not redistribute). Restart the shell."
