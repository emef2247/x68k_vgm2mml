# Release preparation and user native listening

The user reran PSG-source NEMESIS with the default `export_mdx.py` command after
compiler dependency recovery and reports 14/14 exports succeeded. In XM6
TypeG / MMDSP they confirm animation now works. The attached GRA1_01 screenshot
shows highlighted keyboards and meter activity. This is a user native display
observation; do not infer strict waveform fidelity or all-song ending behavior.
The agent did not reconvert private fixtures.

The current GRA1_01 TXT from that user run reports 16128 us/tick and @t193,
with maximum output boundary movement 350 source samples. Earlier pasted
`Missing --mxc tool` diagnostics belong to a failed export; the current success
TXT has no such diagnostic. Saved output versions must be distinguished.

README now explains normalization precision at the start, documents the current
8ms default, whole-gate omission before normalization, the shared timing bound,
and Japanese interpretation of the plain TXT sections. The user-authored README
organization is retained; the outdated provisional 8ms statement is corrected.

`bash scripts/setup_tools.sh` prepares hash-checked MXC, pinned run68x and the
locked Rust helper outside outputs. `--with-mdxtools` additionally prepares
the pinned independent metadata/decompiler tools. System prerequisites are
documented; the script does not run sudo or install globally. Git source edits
and unexpected MXC binaries are not overwritten. A local setup manifest records
installed hashes and revisions. Shell scripts are checked out with LF for WSL.

Validation: Bash syntax and help checks passed; actual `--with-mdxtools` setup
and a repeated run both completed. The optional profile performed a fresh
mdxtools clone/submodule checkout/build. MXC's existing installation was verified
against its fixed hash, and run68/Rust helper were rebuilt. A single public
`opm/from_fm/block_boundary` default export succeeded through compilation and
replay under `outputs/release_setup_public/`; the newly installed independent
`mdxinfo -u -H` reports `Success`, 9 tracks and the expected title. No broad
conversion regression or private listening run was performed by the agent.

Fresh LH1 extraction was also checked in a temporary directory: extracted MXC
is 9946 bytes and matches the pinned compiler SHA256. The complete setup run
reused installed MXC; this separate check exercises extraction without replacing
the active compiler. A focused release review found no blocker. The user's final
instruction is to leave all current changes uncommitted for branch -> PR -> main;
no commit, push or branch switch was performed for this release-preparation work.
