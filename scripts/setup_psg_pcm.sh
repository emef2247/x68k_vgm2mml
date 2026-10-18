#!/usr/bin/env bash
# External runtime stays local; do not vendor emulator sources or binaries.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
repo="$root/.tools/emu2149"
url=https://github.com/digital-sound-antiques/emu2149.git
revision=441f3dc295a9b82db16921461f0678b483db8304
for prerequisite in git gcc; do
    command -v "$prerequisite" >/dev/null || { printf 'Missing prerequisite: %s\n' "$prerequisite" >&2; exit 1; }
done
mkdir -p "$root/.tools"
if [[ ! -e "$repo" ]]; then git clone "$url" "$repo"; fi
if [[ $(git -C "$repo" remote get-url origin) != "$url" ]]; then
    printf 'Unexpected repository at %s; preserve it before setup.\n' "$repo" >&2; exit 1
fi
if ! git -C "$repo" diff --quiet || ! git -C "$repo" diff --cached --quiet; then
    printf 'Local core changes at %s; preserve them before setup.\n' "$repo" >&2; exit 1
fi
if ! git -C "$repo" cat-file -e "$revision^{commit}" 2>/dev/null; then git -C "$repo" fetch origin "$revision"; fi
git -C "$repo" checkout --detach "$revision"
test "$(git -C "$repo" rev-parse HEAD)" = "$revision"
printf 'PSG PCM runtime ready: emu2149 %s\n' "$revision"
