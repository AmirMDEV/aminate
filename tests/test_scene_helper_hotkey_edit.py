"""Offscreen Qt interactions with real Scene Helpers hotkey validation.

Maya persistence and global hotkey installation are mocked. No Maya is started.
"""
import os
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
import maya_timing_tools as timing


class SceneHelperHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        for target, name, kwargs in (
            (timing, "install_tween_machine_hotkey", {}),
            (timing, "_save_option_var_string", {}),
            (timing.maya_floating_channel_box, "install_global_hotkey", {}),
            (timing.maya_floating_channel_box, "set_hotkey", {"side_effect": lambda value: value}),
            (timing.maya_floating_channel_box, "set_graph_editor_hotkey", {"side_effect": lambda value: value}),
            (timing.crash_recovery, "bootstrap_crash_recovery", {}),
        ):
            mocked = patch.object(target, name, **kwargs)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.controller = timing.MayaTimingToolsController()
        self.controller.tween_machine_hotkey = timing.DEFAULT_TWEEN_MACHINE_HOTKEY
        self.controller.floating_channel_box_hotkey = timing.maya_floating_channel_box.DEFAULT_HOTKEY
        self.controller.floating_graph_editor_hotkey = timing.maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY
        self.window = timing.MayaTimingToolsWindow(self.controller)
        self.addCleanup(self.window.deleteLater)
        self.window.show()
        self.app.processEvents()
        disclosure = self.window.findChild(QtWidgets.QWidget, "aminateSection_Floating_windows")
        self.assertIsNotNone(disclosure)
        disclosure.setExpanded(True)
        self.app.processEvents()
        self.window._set_status = Mock()
        self.rows = (
            ("tween", self.window.tween_machine_hotkey_edit, self.window.set_tween_machine_hotkey_button,
             self.window.reset_tween_machine_hotkey_button, "tween_machine_hotkey", timing.DEFAULT_TWEEN_MACHINE_HOTKEY),
            ("channel", self.window.floating_channel_hotkey_edit, self.window.set_floating_channel_hotkey_button,
             self.window.reset_floating_channel_hotkey_button, "floating_channel_box_hotkey", timing.maya_floating_channel_box.DEFAULT_HOTKEY),
            ("graph", self.window.floating_graph_hotkey_edit, self.window.set_floating_graph_hotkey_button,
             self.window.reset_floating_graph_hotkey_button, "floating_graph_editor_hotkey", timing.maya_floating_channel_box.DEFAULT_GRAPH_EDITOR_HOTKEY),
        )

    def test_visible_apply_reset_and_current_binding_for_every_helper(self):
        instruction = self.window.findChild(QtWidgets.QLabel, "sceneHelpersHotkeyInstructions")
        self.assertIn("Leaving the field does not save", instruction.text())
        for key, edit, apply, reset, attribute, default in self.rows:
            with self.subTest(helper=key):
                self.assertTrue(edit.isVisible())
                self.assertTrue(apply.isVisible())
                self.assertTrue(reset.isVisible())
                self.assertEqual(apply.text(), "Apply Hotkey")
                self.assertEqual(reset.text(), "Reset Default")
                self.assertFalse(apply.autoDefault())
                self.assertFalse(reset.autoDefault())
                self.assertIn(default, reset.toolTip())
                label = self.window._helper_hotkey_controls(key)[1]
                self.assertTrue(label.isVisible())
                self.assertEqual(label.text(), "Current binding: " + getattr(self.controller, attribute))
                self.assertTrue(timing.maya_floating_channel_box._is_text_entry_widget(edit))

    def test_capture_and_focus_loss_keep_draft_until_apply_then_reset(self):
        for key, edit, apply, reset, attribute, default in self.rows:
            with self.subTest(helper=key):
                event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_K, QtCore.Qt.ControlModifier, "k")
                QtWidgets.QApplication.sendEvent(edit, event)
                self.assertEqual(edit.text(), "Ctrl+K")
                edit.editingFinished.emit()
                self.assertEqual(getattr(self.controller, attribute), default)
                self.window._sync_from_controller()
                self.assertEqual(edit.text(), "Ctrl+K", "Refresh must retain unapplied draft")
                self.assertIn("unapplied change", self.window._helper_hotkey_controls(key)[1].text())
                QtTest.QTest.mouseClick(apply, QtCore.Qt.LeftButton)
                self.assertEqual(getattr(self.controller, attribute), "Ctrl+K")
                self.assertEqual(self.window._helper_hotkey_controls(key)[1].text(), "Current binding: Ctrl+K")
                QtTest.QTest.mouseClick(reset, QtCore.Qt.LeftButton)
                self.assertEqual(getattr(self.controller, attribute), default)
                self.assertEqual(edit.text(), default)

    def test_invalid_and_conflicting_drafts_remain_reviewable_without_saved_overwrite(self):
        for key, edit, apply, reset, attribute, default in self.rows:
            with self.subTest(helper=key):
                other = next(row for row in self.rows if row[0] != key)
                for candidate in ("", "NoSuchKeyName", getattr(self.controller, other[4])):
                    edit.setText(candidate)
                    apply.click()
                    self.assertEqual(getattr(self.controller, attribute), default)
                    self.assertEqual(edit.text(), candidate)
                    self.window._sync_from_controller()
                    self.assertEqual(edit.text(), candidate)
                    self.assertIn(default, self.window._helper_hotkey_controls(key)[1].text())
                    message, success = self.window._set_status.call_args.args
                    self.assertFalse(success)
                    self.assertIn("Current binding remains " + default, message)

    def test_conflicting_reset_keeps_saved_binding_and_reports_conflict(self):
        for key, edit, apply, reset, attribute, default in self.rows:
            with self.subTest(helper=key):
                other = next(row for row in self.rows if row[0] != key)
                other_original = getattr(self.controller, other[4])
                setattr(self.controller, attribute, "Ctrl+K")
                setattr(self.controller, other[4], default)
                reset.click()
                self.assertEqual(getattr(self.controller, attribute), "Ctrl+K")
                self.assertEqual(edit.text(), default)
                self.assertIn("Ctrl+K", self.window._helper_hotkey_controls(key)[1].text())
                message, success = self.window._set_status.call_args.args
                self.assertFalse(success)
                self.assertIn("already uses", message)
                setattr(self.controller, attribute, default)
                setattr(self.controller, other[4], other_original)

    def test_tween_hotkey_does_not_open_while_text_entry_has_focus(self):
        manager = timing.TweenMachineHotkeyManager(self.controller, "Ctrl+K")
        self.addCleanup(manager.shutdown)
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_K, QtCore.Qt.ControlModifier, "k")
        with patch.object(timing.maya_floating_channel_box, "_has_text_entry_focus", return_value=True), \
                patch.object(timing, "_show_tween_machine_popup") as show:
            self.assertFalse(manager.eventFilter(self.window.tween_machine_hotkey_edit, event))
            show.assert_not_called()


if __name__ == "__main__":
    unittest.main()
