#!/usr/bin/env bash
# Install pinned external tools locally; never install globally or under outputs.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tools="$root/.tools"
with_mdxtools=false
with_psg_pcm=false
with_zmusic=false
for option in "$@"; do
    case "$option" in
        --with-mdxtools) with_mdxtools=true ;;
        --with-psg-pcm) with_psg_pcm=true ;;
        --with-zmusic) with_zmusic=true ;;
        --help|-h)
            printf '%s\n' 'Usage: bash scripts/setup_tools.sh [--with-mdxtools] [--with-psg-pcm] [--with-zmusic]' \
                'Installs MXC v1.01, pinned run68x and the locked Rust helper.' \
                '--with-mdxtools also builds mdxinfo, pdxinfo, mdxdump and mdx2mml.' \
                '--with-psg-pcm also prepares the external emu2149 runtime.' \
                '--with-zmusic also extracts the ZMUSIC 3.02C programs (ZMSC3.X, ZMC.X, ZP3.R) for ZMD playback checks.' \
                'Requires Python 3, curl, git, CMake, make, a C compiler and Rust/Cargo.' \
                'A fresh MXC or ZMUSIC installation also requires lha or lhasa (LH1 support).'
            exit 0 ;;
        *) printf 'Unknown option: %s\n' "$option" >&2; exit 2 ;;
    esac
done

for required in python3 curl git cmake make cc sha256sum; do
    if ! command -v "$required" >/dev/null; then
        printf 'Missing prerequisite: %s. See docs/mdx_compiler_setup.md\n' "$required" >&2
        exit 1
    fi
done
cargo=$(command -v cargo || true)
if [[ -z "$cargo" && -x "$HOME/.cargo/bin/cargo" ]]; then
    cargo="$HOME/.cargo/bin/cargo"
fi
if [[ -z "$cargo" ]]; then
    printf 'Missing Rust/Cargo. See docs/mdx_compiler_setup.md\n' >&2
    exit 1
fi

checksum() {
    [[ -f "$2" ]] && printf '%s  %s\n' "$1" "$2" | sha256sum -c - >/dev/null 2>&1
}

checkout() {
    local url=$1 directory=$2 revision=$3
    if [[ ! -e "$directory" ]]; then
        git clone "$url" "$directory"
    fi
    if [[ $(git -C "$directory" remote get-url origin) != "$url" ]]; then
        printf 'Unexpected repository at %s; refusing to change it.\n' "$directory" >&2
        exit 1
    fi
    if ! git -C "$directory" diff --quiet || ! git -C "$directory" diff --cached --quiet; then
        printf 'Local source changes at %s; preserve them before setup.\n' "$directory" >&2
        exit 1
    fi
    if ! git -C "$directory" cat-file -e "$revision^{commit}" 2>/dev/null; then
        git -C "$directory" fetch origin "$revision"
    fi
    git -C "$directory" checkout --detach "$revision"
    [[ $(git -C "$directory" rev-parse HEAD) == "$revision" ]]
}

mxc_hash=38def25dae39ae35a16668f086843ae9f0d00295e50fd034b7b4108f7c762086
archive_hash=4d4a6f00a100c728f5f4b217998e66ca8e6fa530cdfe1a5ee7c03f70715d98c4
mkdir -p "$tools/mxc"
if ! checksum "$mxc_hash" "$tools/mxc/mxc.x"; then
    if [[ -e "$tools/mxc/mxc.x" ]]; then
        printf 'Existing MXC hash differs; refusing to overwrite %s\n' "$tools/mxc/mxc.x" >&2
        exit 1
    fi
    decoder=$(command -v lha || command -v lhasa || true)
    if [[ -z "$decoder" ]]; then
        printf 'Missing LH1 decoder. On Ubuntu: sudo apt-get install lhasa\n' >&2
        exit 1
    fi
    archive="$tools/mxc/MDX_TOOL.lzh"
    if ! checksum "$archive_hash" "$archive"; then
        curl --fail --location --retry 3 \
            https://nfggames.com/x68000/Mirrors/x68pub/x68tools/SOUND/MXDRV/MDX_TOOL.lzh \
            --output "$archive.download"
        if ! checksum "$archive_hash" "$archive.download"; then
            printf 'MXC archive checksum mismatch; download retained for inspection.\n' >&2
            exit 1
        fi
        mv -- "$archive.download" "$archive"
    fi
    (cd "$tools/mxc" && "$decoder" x MDX_TOOL.lzh mxc.x mxc.doc)
fi
checksum "$mxc_hash" "$tools/mxc/mxc.x"

checkout https://github.com/kg68k/run68x.git "$tools/run68x" \
    fc28826dd795b1f0a3241f0b03fe2353e12e7233
cmake -S "$tools/run68x" -B "$tools/run68x/build" \
    -DCMAKE_C_FLAGS=-Wno-error=format-truncation
cmake --build "$tools/run68x/build" -j2
"$cargo" build --release --locked --manifest-path "$root/scripts/mdx_fixture_generator/Cargo.toml"

if "$with_mdxtools"; then
    checkout https://github.com/vampirefrog/mdxtools.git "$tools/mdxtools" \
        9c8539fec2757fcf7c85d1986171b50ebe2ef1e5
    git -C "$tools/mdxtools" submodule foreach --recursive \
        'git diff --quiet && git diff --cached --quiet'
    git -C "$tools/mdxtools" submodule update --init --recursive
    make -C "$tools/mdxtools" mdxinfo pdxinfo mdxdump mdx2mml \
        CC=cc CFLAGS='-O2 -Wall -D_GNU_SOURCE -Ix68ksjis' LIBS=
fi

# ZMUSIC is only a playback-check environment: the converter writes
# ZMD directly and never invokes these programs. The executables
# ship as an LZH archive inside the pinned zmusic3 checkout.
zmusic_revision=ce859733704fa99fc1219488ad6f0c905261765f
zmusic_archive_hash=14351bf19418dcf171e38062c82f2207a53ffd97f0ebcaaf21d23634fa515f49
zmsc3_hash=93ffb4bb294b0adda0b2c7acd732f7772aa92302b0fc5f532c8aae55abf4130c
zmc_hash=9028b064eb254185d33469fa70cc276259b8b8c8eaba28e24210c1849ba9662c
zp3_hash=690eaea6e819f736b860144f3c1009d8187a2641adb6a37642fd62b5cec6375b
if "$with_zmusic"; then
    checkout https://github.com/kg68k/zmusic3.git "$tools/zmusic3" \
        "$zmusic_revision"
    zmusic_archive="$tools/zmusic3/archives/ZM302C_X.LZH"
    if ! checksum "$zmusic_archive_hash" "$zmusic_archive"; then
        printf 'ZMUSIC archive checksum mismatch: %s\n' "$zmusic_archive" >&2
        exit 1
    fi
    mkdir -p "$tools/zmusic"
    if ! checksum "$zmsc3_hash" "$tools/zmusic/ZMSC3.X" \
        || ! checksum "$zmc_hash" "$tools/zmusic/ZMC.X" \
        || ! checksum "$zp3_hash" "$tools/zmusic/ZP3.R"; then
        for name in ZMSC3.X ZMC.X ZP3.R; do
            if [[ -e "$tools/zmusic/$name" ]]; then
                printf 'Existing ZMUSIC file hash differs; refusing to overwrite %s\n' \
                    "$tools/zmusic/$name" >&2
                exit 1
            fi
        done
        decoder=$(command -v lha || command -v lhasa || true)
        if [[ -z "$decoder" ]]; then
            printf 'Missing LH1 decoder. On Ubuntu: sudo apt-get install lhasa\n' >&2
            exit 1
        fi
        (cd "$tools/zmusic" && "$decoder" x "$zmusic_archive" ZMSC3.X ZMC.X ZP3.R)
    fi
    checksum "$zmsc3_hash" "$tools/zmusic/ZMSC3.X"
    checksum "$zmc_hash" "$tools/zmusic/ZMC.X"
    checksum "$zp3_hash" "$tools/zmusic/ZP3.R"
fi

python3 - "$tools" "$root" "$with_mdxtools" "$with_zmusic" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import subprocess

tools, root = map(Path, sys.argv[1:3])
binaries = {
    'mxc': tools / 'mxc/mxc.x',
    'run68': tools / 'run68x/build/run68',
    'mdx-fixture-generator': root / 'scripts/mdx_fixture_generator/target/release/mdx-fixture-generator',
}
if sys.argv[3] == 'true':
    binaries.update((name, tools / 'mdxtools' / name)
                    for name in ('mdxinfo', 'pdxinfo', 'mdxdump', 'mdx2mml'))
if sys.argv[4] == 'true':
    binaries.update((name, tools / 'zmusic' / name)
                    for name in ('ZMSC3.X', 'ZMC.X', 'ZP3.R'))
for name, path in binaries.items():
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f'Missing installed binary: {path}')
report = {
    'run68x_revision': subprocess.check_output(
        ['git', '-C', str(tools / 'run68x'), 'rev-parse', 'HEAD'], text=True).strip(),
    'cargo_lock_sha256': hashlib.sha256(
        (root / 'scripts/mdx_fixture_generator/Cargo.lock').read_bytes()).hexdigest(),
    'binaries': {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                 for name, path in binaries.items()},
}
if sys.argv[3] == 'true':
    report['mdxtools_revision'] = subprocess.check_output(
        ['git', '-C', str(tools / 'mdxtools'), 'rev-parse', 'HEAD'], text=True).strip()
if sys.argv[4] == 'true':
    report['zmusic3_revision'] = subprocess.check_output(
        ['git', '-C', str(tools / 'zmusic3'), 'rev-parse', 'HEAD'], text=True).strip()
(tools / 'setup_manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('Setup complete. Installed tools: ' + ', '.join(binaries))
print('Manifest: ' + str(tools / 'setup_manifest.json'))
PY

if $with_psg_pcm; then bash "$root/scripts/setup_psg_pcm.sh"; fi
