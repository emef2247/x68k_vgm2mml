# Migrated OPLL-to-OPM fixture routing

The 16 public `opm/from_fm` inputs contain OPM commands plus AY and SCC
commands retained by the source conversion. Routing previously rejected this
combination even when the retained compatibility chips produced no signal.

AY volumes remain zero throughout all 16 inputs. The initialization writes
are staggered by a few source samples; requiring all three volume writes at
time zero would reject these files unnecessarily. The inventory assumes AY
reset volumes zero, accepts only ordinary registers 0–13, and disqualifies
every nonzero or envelope-volume write. Commands and their counts remain in
the source inventory.

`3ch_test` and `chords_mix` have nonzero SCC volume/frequency writes, so
nonzero volume alone does not establish active sample output. Their SCC
waveform RAM is explicitly zero during every positive-duration enabled,
nonzero-volume interval. Temporary byte-zero `FF`/`00` changes occur at the
same source timestamp. These writes remain source evidence; the route does
not manufacture a positive-duration SCC note from them.

The SCC exemption starts with reset volume/enable zero and treats waveform
RAM as unknown until written. Every potentially active interval must have
all 32 waveform bytes explicitly zero. Unknown RAM and constant nonzero DC
waveforms do not qualify. The new SCC exemption applies only to finite
inputs containing native OPM commands. Every looped input remains used unless
the older undeclared/no-nonzero-volume rule applies: even a disabled final
channel can retain nonzero waveform RAM that a later loop iteration enables.
The new AY exemption likewise requires native OPM commands, preserving the
existing PSG/SCC-only route for silent compatibility inputs.

This is a frontend route decision only. Source traces/Segments are unchanged.
Regression coverage retains used chip identities, tests active mixed-source
rejection, and distinguishes zero-time changes from positive intervals.
