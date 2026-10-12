# OPNA diagnostic FM roundtrip milestone

The user moved 29 public OPNA patterns into this repository and selected
codex/mucom88. MUCOM MML is only a validation target; normal X68000 output is
MDX MML, with future PCM IR. README keeps attribution/license notices but no
MUCOM-output user workflow. OPNA-to-OPM at 4 MHz will use the vgm-conv mapping
in a separate target stage; record that adoption in README when implemented.

Native Segments project typed operator/pitch/key/control values to diagnostic
MUCOMVGM register-MML. One track preserves both ports' write order. C192/T55125
is a virtual sample clock specific to the accepted MUCOMVGM dialect, not an
ordinary PC-8801 MUCOM88 tempo. Target CSV retains source event/Segment IDs.
Compiler frequency-high buffering is normalized at committed lower writes;
repeated prescaler selectors use alternating unused data to survive deduplication.
Source timing/state/bytes remain unchanged.

External v0.0.5 validation: 16 FM-positive cases pass clock, exact sample timing,
control sequence, known State at each boundary, ordered operator edge and final
held-state/end checks. The other13 cases contain only SSG and are reported as
no_active_fm, not additional successful FM coverage. Initial results saved in
outputs/opna_mucom_roundtrip_2026-10-12; WSL retained evidence saved separately
in outputs/opna_mucom_roundtrip_wsl_2026-10-12. No acoustic, PCM or musical
note/instrument rendering equivalence is claimed.

Independent negative checks reject altered target parameters even when the
compiler stream agrees with them, changed initialization, lost final wait and
same-sample key order corruption. External synthetic coverage includes all six
channels, cross-port latch commits, CH3, repeated prescaler strobes, held EOF
and finite replay of a declared loop. Architect review caught potential false
success for unexpanded DAC streams/unknown writes: the runner now rejects both
before compilation, with negative tests mixing them with real FM keys.

The public FM/PSG references match29/29 existing project public OPM references;
the pattern fixture directories are included with provenance documentation.
Diff whitespace checking has one inherited blank-at-EOF notice in the migrated
PSG retrigger reference MML; preserve its original bytes rather than editing
source context. New Python modules/tests use LF line endings.
Separately expanded Ancient/Onion MUCOM song archives remain local third-party
material with their original notices, not part of this commit or published
derived test artifacts.

Final WSL focused run:29 tests pass, including real mucomvgm.exe execution and
unknown-write/stream rejection. Windows and WSL public fixture batches each
report16 passed and13 no_active_fm. Fresh public/synthetic regression:654 tests,
9 failures/11 errors/3 skips. All20 failure identities match the earlier run;
HEAD reproduction evidence is recorded in the prior source-stage note.
The user accepts FM-only coverage now and requests FM/SSG next. Treat SSG as
PSG-equivalent musical behavior, with source Segments and MML roundtrip coverage;
the13 SSG-only fixtures must become positive SSG coverage at that milestone.
The user authorizes repository reflection at this milestone; create a local
commit on codex/mucom88 after checks. No push or private fixture checks requested.
