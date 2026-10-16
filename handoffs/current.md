# PCM profiles and batch timeout checkpoint (2026-10-17)

Current user request: ultra_low (=quarter standard PCM rate) after low-profile
regression still showed native ADPCM buffer errors. Both worktrees saved;
no stage/commit/push/branch changes. User owns private regression and listening.

--pcm-profile standard|low|ultra_low defaults to standard. Shared immutable
py/pcm_profiles.py exactly matches MUCOM. x68k derived SegaPCM/live Delta uses
F4/15625Hz/8sec, F2/7812.5Hz/16sec or F0/3906.25Hz/32sec. F0 requires4MHz/div1024;
analysis, playback and bridge metadata use the selected clock, not fixed8MHz.
Final shared MDX-clock alignment uses actual selected rate and nearest positive
even sample count. Source State/Segments/PCM IR remain intact.

Independent Delta and native MSM use capped nearest supported rates; ultra caps
toF0. Native MSM original .pcm_* retained, target .pcm_low.pcm_* or
.pcm_ultra_low.pcm_* separate. Profile JSON/mapping/losses record actual profile,
source gates/IDs, rates, bytes and duration error. Already-in-range bytes retained
without fake loss. Source reset/cadence/mode guards and96slots/65535bytes/sample
verified scope/force capacity rules remain unchanged.

Both export_mdx/export_mucom batch signatures and CLI parser defaults now600s
per input per stage. Explicit --timeout remains effective. Internal helper
subprocess budgets are separate and unchanged. Canonical CLI has no new timeout.
MUCOM MSM/Sega uses actual rounded Delta-N4615 for ultra (1499875/384Hz), not
MDX F0 rules. Native OPNA ADPCM in MUCOM remains outside this profile scope.

Checks after saving: x68k7 focused authored checks passed, including standard/
low behavior, ultra quarter payload/F0/clock/dumps/alignment, native/independent/
live Delta source preservation, parser and batch default600/explicit17 forwarding.
MUCOM3 focused authored checks passed. Public authored SEGAONE canonical ultra
with --dump-passes generated MML+helper MDX/PDX at
outputs/diagnostics/pcm_ultra_low_20261017. Inspected bridge4M/div1024/F0,
rate3906.25, MML P F0, payload2048bytes confirmed in PDX table; standard prior8190,
low4095. Native artifacts retained. No private conversions or native listening.

Inverse-rate chunk32sec keeps maximum waveform chunk about62500bytes like low/
standard. Total bank size and slots can shrink; single-sample buffer requirement
need not. No runtime-fit guarantee; linear interpolation has no AA filter.
Read docs/pcm_profiles.md for scope, reports and loss. Next allowed action: user
regression in a separate outdir with --pcm-profile ultra_low; no private batch
reruns or broad scope expansion without user direction.

External field_notes/2026-10-17_pcm_ultra_low_profile.md records user regression
and new implementation. Prior low/noise history remains in2026-10-16 notes;
do not resume paused VGM output or broaden PSG/noise/force here.
