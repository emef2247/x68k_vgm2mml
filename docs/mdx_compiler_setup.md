# Persistent MXC / run68 setup (WSL)

FM-only export defaults to MXC. Keep external tools in ignored `.tools/`,
outside generated `outputs/`. Deleting `outputs/` must not remove dependencies.
The lookup order is explicit `--mxc` / `--run68`, PATH, `.tools/`, then the old
`outputs/research/` locations for compatibility. An invalid explicit path is
an error; no other compiler is silently selected.

The installation below uses the same compiler and runner revision as the
validated 2026-10-09 baseline. Run from the repository root in WSL. Prerequisites
are Python 3, curl, git, CMake, a C compiler and an LHA decoder supporting `-lh1-`
(Ubuntu's `lhasa` package). Do not use Python `lhafile` for this archive: it does
not support that compression method.

The MXC archive is linked by the
[mdxtools compilation instructions](https://github.com/vampirefrog/mdxtools/blob/master/README.md).
MXC v1.01 identifies itself as MFS soft / milk, 1989. Tool binaries are local
dependencies and are not committed or copied into listening packages.

```sh
mkdir -p .tools/mxc
curl -fL https://nfggames.com/x68000/Mirrors/x68pub/x68tools/SOUND/MXDRV/MDX_TOOL.lzh \
  -o .tools/mxc/MDX_TOOL.lzh
printf '%s  %s\n' \
  4d4a6f00a100c728f5f4b217998e66ca8e6fa530cdfe1a5ee7c03f70715d98c4 \
  .tools/mxc/MDX_TOOL.lzh | sha256sum -c -
# Continue only if the checksum check succeeds.
(cd .tools/mxc && lha x MDX_TOOL.lzh mxc.x mxc.doc)
printf '%s  %s\n' \
  38def25dae39ae35a16668f086843ae9f0d00295e50fd034b7b4108f7c762086 \
  .tools/mxc/mxc.x | sha256sum -c -

# Clone once; for an existing installation omit the clone command.
git clone https://github.com/kg68k/run68x.git .tools/run68x
git -C .tools/run68x checkout --detach fc28826dd795b1f0a3241f0b03fe2353e12e7233
cmake -S .tools/run68x -B .tools/run68x/build \
  -DCMAKE_C_FLAGS=-Wno-error=format-truncation
cmake --build .tools/run68x/build -j2
```

The GCC 11 warning flag matches the previous baseline and does not modify
emulator source. The Rust helper is a separate dependency and also lives outside
`outputs/`:

```sh
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python3 scripts/export_mdx.py tests/fixtures/public/opm/from_fm/block_boundary/ \
  --outdir outputs/compiler_smoke
```

After setup the usual export command needs no tool-path options. Alternatively,
use `--mxc /persistent/path/MXC.X --run68 /persistent/path/run68`.
PCM uses the existing typed PCM backend; this setup does not change that route.
