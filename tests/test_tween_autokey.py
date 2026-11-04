"""Tween regressions: real controller writes plus retained Qt signal paths."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import maya_timing_tools as timing


def context(node="ctrl", frame=0.0):
    return {"valid": True, "nodes": [node], "time": frame, "items": [
        {"node": node, "attribute": "translateX", "plug": node + ".translateX",
         "left_value": 0.0, "right_value": 10.0}]}


class TweenControllerTests(unittest.TestCase):
    def test_key_does_not_require_setattr_on_connected_animation(self):
        commands = Mock()
        commands.setAttr.side_effect = RuntimeError("connected plug")
        commands.currentTime.return_value = 8.0
        with patch.object(timing, "MAYA_AVAILABLE", True), patch.object(timing, "cmds", commands):
            success, message = timing.MayaTimingToolsController.apply_tween_machine(
                Mock(), 25, context=context())
        self.assertTrue(success, message)
        commands.setKeyframe.assert_called_once_with("ctrl", attribute="translateX", time=0.0, value=2.5)
        commands.setAttr.assert_not_called()

    def test_failed_key_is_not_reported_as_success(self):
        commands = Mock()
        commands.setKeyframe.side_effect = RuntimeError("locked plug")
        with patch.object(timing, "MAYA_AVAILABLE", True), patch.object(timing, "cmds", commands):
            self.assertFalse(timing.MayaTimingToolsController.apply_tween_machine(Mock(), 50, context=context())[0])
        self.assertEqual(commands.undoInfo.call_count, 2)


@unittest.skipUnless(timing.QtWidgets, "Qt unavailable")
class TweenPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = timing.QtWidgets.QApplication.instance() or timing.QtWidgets.QApplication([])

    def setUp(self):
        self.controller = Mock(tween_machine_opacity=1.0)
        self.controller.build_tween_machine_context.return_value = context()
        self.controller.apply_tween_machine.return_value = (True, "keyed")
        self.popup = timing.TweenMachinePopup(self.controller)

    def tearDown(self):
        self.popup._apply_timer.stop()
        self.popup.hide()

    def test_slider_timer_keys_without_release(self):
        self.popup.slider.setValue(75)
        self.popup._apply_timer.timeout.emit()
        self.controller.apply_tween_machine.assert_called_once_with(75, context=self.popup.context, key=True)

    def test_clicking_same_tick_still_keys(self):
        self.popup._set_slider_value(50)
        self.controller.apply_tween_machine.assert_called_once_with(50, context=self.popup.context, key=True)

    def test_same_value_on_new_selection_and_frame_refreshes_target(self):
        self.popup._set_slider_value(50)
        updated = context("other", 12.0)
        self.controller.build_tween_machine_context.return_value = updated
        commands = Mock()
        commands.currentTime.return_value = 12.0
        with patch.object(timing, "MAYA_AVAILABLE", True), patch.object(timing, "cmds", commands), \
                patch.object(timing, "_selected_transform_nodes", return_value=["other"]):
            self.popup._apply_current_value(create_history=False)
        self.controller.apply_tween_machine.assert_called_with(50, context=updated, key=True)

    def test_failed_value_can_be_retried(self):
        self.controller.apply_tween_machine.return_value = (False, "not keyed")
        self.popup._apply_current_value(create_history=False)
        self.popup._apply_current_value(create_history=False)
        self.assertEqual(self.controller.apply_tween_machine.call_count, 2)

    def test_slider_groove_click_and_drag_use_absolute_percentage(self):
        from PySide6.QtTest import QTest
        slider = self.popup.slider
        slider.resize(300, 30)
        released = Mock()
        slider.sliderReleased.connect(released)
        QTest.mousePress(slider, timing.QtCore.Qt.LeftButton, pos=timing.QtCore.QPoint(225, 15))
        self.assertTrue(74 <= slider.value() <= 78, slider.value())
        QTest.mouseRelease(slider, timing.QtCore.Qt.LeftButton, pos=timing.QtCore.QPoint(30, 15))
        self.assertTrue(5 <= slider.value() <= 12, slider.value())
        released.assert_called_once()


if __name__ == "__main__":
    unittest.main()
