"""Preserve key identities during frame snapping; report retime failures."""
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import maya_timing_tools as timing


class TimingAuditTests(unittest.TestCase):
    def test_snap_preserves_values_and_count_without_time_collisions(self):
        for times in ([0, 0.1, 1], [-1, -0.1, 0], [0.6, 1.4, 3.2], [0, 1, 2], [0.25]):
            with self.subTest(times=times):
                keys = {float(t): "pose{}".format(i) for i, t in enumerate(times)}
                def keyframe(node, **kwargs):
                    if kwargs.get("query"):
                        return sorted(keys)
                    source = kwargs["time"][0]
                    target = source + kwargs["timeChange"]
                    self.assertNotIn(target, keys, "move would collide with an existing key")
                    keys[target] = keys.pop(source)
                with patch.object(timing, "cmds", Mock(keyframe=keyframe)):
                    timing._snap_curve_times("ctrl", "translateX")
                self.assertEqual(len(keys), len(times))
                self.assertEqual([keys[t] for t in sorted(keys)], ["pose{}".format(i) for i in range(len(times))])
                self.assertTrue(all(t == round(t) for t in keys))

    def test_retime_total_and_partial_failure_are_explicit(self):
        for failures, expected in (([RuntimeError("locked"), RuntimeError("locked")], "failed"),
                                   ([1, RuntimeError("locked")], "partial")):
            commands = Mock()
            commands.keyframe.return_value = [0, 1]
            commands.currentTime.return_value = 5
            with patch.object(timing, "MAYA_AVAILABLE", True), patch.object(timing, "cmds", commands), \
                    patch.object(timing, "_selected_transform_nodes", return_value=["ctrl"]), \
                    patch.object(timing, "_settable_keyable_attrs", return_value=["translateX", "translateY"]), \
                    patch.object(timing, "_retime_curve_times", side_effect=failures):
                success, message = timing.MayaTimingToolsController.retime_selected_keys_to_every_n_frames(Mock(), 2)
            self.assertFalse(success)
            self.assertIn(expected, message)
            commands.currentTime.assert_called_with(5.0, edit=True)
            if expected == "failed":
                commands.playbackOptions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
