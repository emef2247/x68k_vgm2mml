# Active checkpoint: PDX byte budget enforced (2026-10-21)

User requested 1,200,000-byte PDX cap including table and reuse under pressure.
Implemented/saved; no Git stage/commit/push. User owns local_only regression.

## Current behavior

- pcm_capacity.py centralizes 96slots,65535B/sample,768Btable,1200000Bfile.
- Default budget96: quality sharing then deterministic representative coverage
  within slots AND bytes. Onset repair remains byte-feasible. Reuse existing
  payloads and retain event IDs/times/rates/pan; direct original->final gain/gate
  diagnostics. Source IR unchanged. This does not bound candidate-generation
  working memory/time; candidates are made before selection, before PDX packing.
- Applies to eligible MSM6258,Delta-T,SegaPCM bank/mix. PSG has final guard but
  no approximate sharing. Explicit similar/off reject overflow unless force
  omits whole new samples; retained reuse costs0. Parallel omissions occupy
  no voice. Source errors/reset/control eligibility remain blocking.
- Final project and writer enforce budget; writer checks actual packed file
  including padding and removes oversized output. Decoded5MB workspace excluded.
- Console/results show planned before/after bytes and actual packed cap/fit.
  Actual size remains unknown until current/owned binary evidence. MDX256KiB
  player allocation, compiler/offset restrictions and runtime playback separate.
- Compiler default remains mmlx (export API/CLI and roundtrip CLI), explicit mxc.

## Validation and artifacts

253 public/authored checks passed. Actual helper exact1200000 boundary accepted,
+1 and post-packpaddingoverflow rejected. Authored20*65535B assets->18reps,
20events0omits, sourcehashesunchanged:PDX1311468->1180398B, MDX877B+MML generated.
Inspect outputs/diagnostics/pdx_byte_budget_20261021/inspection.json and CSVs.
Canonical public opm_segapcm4/4 exported with defaultbudget96; result CSV has
PDXbytecap/actualfit. No private conversion/regression/listening.

Docs:pcm_pdx.md,pcm_bank_reduction.md,pcm_bank_shared_sources.md,opna_force.md.
External note:field_notes/2026-10-21_pdx_byte_budget.md.
Prior Fujix measurements:field_notes/2026-10-21_fujix_reference_banks_and_footprint.md;
BR4tables/114assets718130B;GR1table/74assets475413B;41regular16trackMDXstatic scans.
Those measurements are not native playback/peak-polyphony guarantees.

## Completion / supplied user regression (2026-10-22)

Implementation and review complete; no material blocker. Before interruption:
253focusedchecks passed, then8/8 byte checks including1additional case
(254distinct). PublicSega4/4 and authoredcapacityfinal artifacts retained.
No further broad tests or private conversion on resume.
User logs:GFII10/10,ABII4/9,POWRDF6/9,GLOC15/17 exported.41measuredPDX allfit
1200000B; GFII04 1362412->1174924B andGFII06 1281216->1156224B successful.
Ten remaining failures are MDX track-start offset0xfffe overflow, not PDXsize.
Existingstatus pcm_projection_blocked refers to typedMDXbuild; MML/PDXretained.
Do not claim listening/nativeplayback success or silently add an MDXsize bypass.
Externalrecord:field_notes/2026-10-22_pdx_byte_budget_user_regression.md.
Ignoredaggregate:outputs/diagnostics/pdx_byte_budget_20261021/user_regression_20261022.json.
Next: report completion/causes; await user direction on any MDXsize optimization.

## Latest read-only inquiry (2026-10-22)

mmlx0.2.0 has no optimizer flag; soundlog LZ serialized-body support is not
exposed by mmlx and cannot solve pre-layout track-offset overflow.256KiBplayer
allocation remains distinct. No option enabled, no conversion behavior changed.
User reports TBOUR01/02,POWRDF02/05/06,GFII04/06 ADPCM-buffer warnings.
All7 currentoutputs standard/mix/P-only,mostly8s/~62500B chunks,PDX327972–1174924B.
Five part_resource_limit bank fallbacks; TBOUR01/POWRDF02 sample_loop fallback.
Published+diagnosticPDX equal. Actual user-loadedcopies/buffer setting unmeasured.
Public MMDSPMACTRL LOAD_PDX returns PCM-bufferinsufficient if wholePDXtransfer
fails;1200000NanoDrive8budget does not certify MMDSP/MADRV capacity. No invented
256KB/320KB PCM default. Existing low/ultra_low reduce total but retain~62.5KB
maxchunks by longer16/32s chunks. No private reconversion/tests/listening.
Record:field_notes/2026-10-22_mmlx_size_and_pcm_buffer_comparison.md.
No MDX optimizer, smaller playbackprofile or bankresource change implemented;
these are possible next work, pending user direction.

User follow-up:from_Fujix/mslug confirmed DACstream0/type04 longADPCM,1–2blocks,
~1.03–1.13MB total, observedSTOP/PLAY epochs. No MDX/PDX supplied in thatfolder.
Useful continuity/reference, not proof of MMDSP on-demand disk streaming or
lower wholePDX memory. Few longslots alone do not reduce storedsize. Details
appended to latest inquiryFieldNote; no conversion/backend change.

Raizing reference recheck (read-only):BR PDX718130B/114assets/median5321B,
GR475413B/74assets/median3514B; no asset>=60000B. BR_BBAR22refs/1248encodedNOTE,
GR_B068refs/261encodedNOTE, no repeat expansion or acoustic-count claim.
Direct sample-bank reference, unlike mslug VGM supplystream. Reference PDXs
larger than warning332832/327972B outputs; total-byte-only runtime diagnosis
remains unproven without same-environment playback evidence. Do not infer
selective loading from per-song used-asset sums. No conversion/code changes.
Record:field_notes/2026-10-22_raizing_reference_bank_reuse.md.

## Next allowed action / remaining boundaries

User runs local_only regression and listening, then review reported size/reuse
metrics. Prior budget96/common MSM6258/Delta-T bank work remains saved and tested.
Do not raise slot count to claim multibank support, crop streams or invent
independent decoder starts. No true multibank assembler/runtime support yet.
Do not resume enhancer/PSG musical cutout audit, private regression or unrelated
optimization unasked. Preserve prior unrelated work/Japanese document copies
and external notes. Public working tree does not include external private notes.
