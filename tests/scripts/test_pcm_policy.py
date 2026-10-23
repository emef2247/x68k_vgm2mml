"""PCM auto policy is selected from actual source supply, not declarations."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from msm6258 import analyze
from pcm_mdx import project
from pcm_assessment import ProjectionError
from generate_pcm_fixtures import vgm,write,wait,playback,data_block,stream_setup,stream_fast_start,stream_cases


def mixed():
    return vgm(data_block(bytes.fromhex('12 34 56 78'))+stream_setup()+
        write(0,1)+write(0,2)+write(1,0x9a)+stream_fast_start()+
        wait(8)+write(1,0xbc)+wait(1220)+write(0,1))


class PcmPolicyTests(unittest.TestCase):
    def test_default_auto_keeps_direct_source_strict(self):
        body,_=playback(bytes(range(32)))
        native=analyze(vgm(body));plan=project(native,stem='direct')
        selection=plan.assessment.as_dict()['policy_selection']
        self.assertEqual(selection['requested'],'auto')
        self.assertEqual(selection['effective'],'strict')
        self.assertEqual(selection['stream_supply_count'],0)
        self.assertEqual(selection['reason'],'no_observed_dac_stream_supplies')

    def test_unused_stream_setup_does_not_enable_loss(self):
        body,_=playback(bytes(range(32)))
        native=analyze(vgm(data_block(bytes.fromhex('12 34'))+stream_setup()+body))
        self.assertFalse(native.stream_supplies)
        self.assertEqual(project(native,stem='unused').assessment.policy,'strict')

    def test_auto_selects_best_effort_for_mixed_source(self):
        native=analyze(mixed());before=repr(native)
        plan=project(native,stem='mixed')
        selection=plan.assessment.as_dict()['policy_selection']
        self.assertEqual(selection['effective'],'best-effort')
        self.assertEqual(selection['reason'],'observed_dac_stream_supplies')
        self.assertEqual(selection['stream_supply_count'],4)
        self.assertEqual(repr(native),before)
        loss=next(i for i in plan.assessment.items if i['code']=='byte_supply_schedule_not_preserved')
        self.assertEqual(loss['source_value']['direct_supplied_bytes'],2)
        self.assertEqual(loss['source_value']['stream_supplied_bytes'],4)
        with self.assertRaises(ProjectionError):
            project(native,stem='mixed_strict',policy='strict')

    def test_direct_irregular_needs_explicit_best_effort(self):
        native=analyze(vgm(write(0,1)+write(0,2)+write(1,0x12)+wait(30)+write(1,0x34)+wait(1000)+write(0,1)))
        with self.assertRaises(ProjectionError) as caught:
            project(native,stem='direct_auto')
        self.assertEqual(caught.exception.assessment.policy_selection['effective'],'strict')
        plan=project(native,stem='direct_best',policy='best-effort')
        self.assertEqual(plan.assessment.policy_selection['reason'],'explicit_policy')
        self.assertTrue(any(u.kind=='pcm_note' for u in plan.units))

    def test_auto_does_not_hide_unresolved_stream_configuration(self):
        raw=next(raw for name,raw,_ in stream_cases() if name=='stream_delayed_chip_stop')
        native=analyze(raw)
        from dataclasses import replace
        bad=replace(native,playbacks=(replace(native.playbacks[0],decoder_reset_known=False,
            issues=('irregular_byte_supply','decoder_start_unknown_or_continuation')),))
        with self.assertRaises(ProjectionError):project(bad,stem='unknown')

    def test_profiled_mixed_source_retains_supply_choice(self):
        from pcm_msm_profile import project as smaller
        native=analyze(mixed());low=smaller(native,pcm_profile='low')
        plan=project(low,stem='low_mixed')
        self.assertEqual(plan.assessment.policy,'best-effort')
        self.assertTrue(any(i['code']=='byte_supply_schedule_not_preserved' for i in plan.assessment.items))


if __name__=='__main__':unittest.main()
