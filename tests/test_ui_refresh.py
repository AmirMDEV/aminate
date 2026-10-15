"""Qt routing checks for v0.3.8. Scene queries are mocked, not live Maya QA."""
import importlib
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from PySide6 import QtWidgets
except ImportError:
    try:
        from PySide2 import QtWidgets
    except ImportError:
        QtWidgets = None


def scene_queries():
    cmds = Mock()
    for name in ('ls', 'listRelatives', 'filterExpand', 'listConnections'):
        getattr(cmds, name).return_value = []
    cmds.objExists.return_value = False
    cmds.currentTime.return_value = 1.
    cmds.playbackOptions.return_value = 24.
    cmds.file.return_value = ''
    cmds.optionVar.return_value = False
    return cmds


class PackagePromptTests(unittest.TestCase):
    def test_unnamed_scene_prompts_without_saving(self):
        import maya_reference_manager as ref
        cmds = scene_queries()
        cmds.about.return_value = False
        with patch.object(ref, 'MAYA_AVAILABLE', True), patch.object(ref, 'cmds', cmds), patch.object(ref, '_scene_path', return_value=''):
            with self.assertRaisesRegex(RuntimeError, 'Save your Maya scene first'):
                ref.ReferencePackageController().package_current_scene()
        cmds.confirmDialog.assert_called_once()
        self.assertEqual(cmds.confirmDialog.call_args.kwargs['title'], 'Save Scene First')
        self.assertFalse(any(c.kwargs.get('save') for c in cmds.file.call_args_list))

    def test_named_scene_missing_on_disk_also_prompts(self):
        import maya_reference_manager as ref
        cmds = scene_queries()
        cmds.about.return_value = False
        with patch.object(ref, 'MAYA_AVAILABLE', True), patch.object(ref, 'cmds', cmds), patch.object(ref, '_scene_path', return_value='/missing/scene.ma'), patch.object(ref.os.path, 'isfile', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Save your Maya scene first'):
                ref.ReferencePackageController().package_current_scene()
        cmds.confirmDialog.assert_called_once()

    def test_batch_unnamed_scene_fails_without_modal(self):
        import maya_reference_manager as ref
        cmds = scene_queries()
        cmds.about.return_value = True
        with patch.object(ref, 'MAYA_AVAILABLE', True), patch.object(ref, 'cmds', cmds), patch.object(ref, '_scene_path', return_value=''):
            with self.assertRaises(RuntimeError):
                ref.ReferencePackageController().package_current_scene()
        cmds.confirmDialog.assert_not_called()

    def test_version_and_installers_load_same_manifest(self):
        import aminate_package_manifest as manifest
        data = json.loads((ROOT / 'manifest.json').read_text())
        self.assertEqual(data['release_tag'], 'v0.3.8')
        self.assertEqual(data['version'], manifest.RELEASE_VERSION_LABEL)
        self.assertEqual(data['runtime_files'], list(manifest.RUNTIME_FILES))
        self.assertIn('maya_aminate_ui.py', data['runtime_files'])
        for name in data['installer_files']:
            spec = importlib.util.spec_from_file_location('installer_test', ROOT / name)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module._load_manifest(str(ROOT))['version'], data['version'])

    def test_graph_editor_outliner_reuses_existing_panes(self):
        import maya_floating_channel_box as floating
        cmds = Mock()
        cmds.scriptedPanel.return_value = 'graphControl'
        cmds.outlinerPanel.return_value = 'outlinerControl'
        with patch.object(floating, 'cmds', cmds), patch.object(floating, '_resize_graph_editor_split'), patch.object(floating, '_GRAPH_EDITOR_SHOW_OUTLINER', True):
            floating.set_graph_editor_outliner_visible(False)
            self.assertFalse(floating._GRAPH_EDITOR_SHOW_OUTLINER)
            cmds.paneLayout.assert_any_call(floating.GRAPH_EDITOR_PANE_NAME, edit=True, setPane=('graphControl', 1))
            cmds.paneLayout.assert_any_call(floating.GRAPH_EDITOR_PANE_NAME, edit=True, configuration='single')
            floating.set_graph_editor_outliner_visible(True)
            cmds.paneLayout.assert_any_call(floating.GRAPH_EDITOR_PANE_NAME, edit=True, setPane=('outlinerControl', 1))
            cmds.paneLayout.assert_any_call(floating.GRAPH_EDITOR_PANE_NAME, edit=True, setPane=('graphControl', 2))
            cmds.deleteUI.assert_not_called()

    def test_channel_records_can_read_pinned_nodes(self):
        import maya_floating_channel_box as floating
        with patch.object(floating, '_selected_nodes') as selection, patch.object(floating, '_attr_names_for_node', return_value=[]) as attributes:
            self.assertEqual(floating.channel_records_for_selection(['pinnedCtrl']), [])
            selection.assert_not_called()
            attributes.assert_called_once_with('pinnedCtrl')


@unittest.skipUnless(QtWidgets, 'PySide is required for Qt checks')
class UiRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def window(self, module_name, window_name, controller_name):
        module = importlib.import_module(module_name)
        mocked = patch.object(module, 'cmds', scene_queries())
        mocked.start(); self.addCleanup(mocked.stop)
        window = getattr(module, window_name)(getattr(module, controller_name)())
        self.addCleanup(window.deleteLater)
        return window

    def test_hold_selection_changes_primary_action(self):
        window = self.window('maya_contact_hold', 'MayaContactHoldWindow', 'MayaContactHoldController')
        window._sync_from_controller = Mock()
        table = window.holds_table
        self.assertFalse(window.apply_button.isHidden())
        table.setRowCount(1)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem('Hold'))
        table.selectRow(0)
        self.assertTrue(window.apply_button.isHidden())
        self.assertFalse(window.update_button.isHidden())
        table.clearSelection()
        self.assertFalse(window.apply_button.isHidden())

    def test_retarget_scope_dispatches_once(self):
        window = self.window('maya_face_retarget', 'MayaFaceRetargetWindow', 'FaceRetargetController')
        window._retarget_all_pairs = Mock()
        selected = Mock()
        window._retarget_selected_pairs = selected
        window.retarget_all_button.click()
        window._retarget_all_pairs.assert_called_once()
        selected.assert_not_called()
        window.retarget_scope.setCurrentIndex(1)
        window.retarget_all_button.click()
        selected.assert_called_once()
        window._retarget_all_pairs.assert_called_once()

    def test_onion_reenable_restores_callbacks(self):
        window = self.window('maya_onion_skin', 'MayaOnionSkinWindow', 'MayaOnionSkinController')
        window._apply_settings = Mock()
        window._populate_from_controller = Mock()
        window.controller = Mock()
        window.controller.manual_refresh.return_value = (True, 'Ready')
        window.onion_enabled.setChecked(True)
        window.controller._register_callbacks.assert_called_once()
        window.onion_enabled.setChecked(False)
        window.controller.detach.assert_called_once_with(clear_attachment=False)

    def test_unified_offset_dispatch(self):
        window = self.window('maya_dynamic_parenting_tool', 'MayaDynamicParentingWindow', 'MayaDynamicParentingController')
        window.save_offset_button.clicked.disconnect()
        window.save_offset_row_button.clicked.disconnect()
        pending, selected = Mock(), Mock()
        window.save_offset_button.clicked.connect(pending)
        window.save_offset_row_button.clicked.connect(selected)
        window._selected_target_ids = Mock(return_value=[])
        window.save_current_offset_button.click()
        pending.assert_called_once(); selected.assert_not_called()
        window._selected_target_ids.return_value = ['parent']
        window.save_current_offset_button.click()
        selected.assert_called_once(); pending.assert_called_once()

    def test_toolbar_pins_update_existing_bar(self):
        import maya_aminate_ui as ui
        import maya_timing_tools as timing
        bar = QtWidgets.QWidget()
        bar._workflow_buttons = {name: QtWidgets.QPushButton(name, bar) for name in ('toolkit_bar', 'history_timeline')}
        previous = ui._session_pins
        self.addCleanup(setattr, ui, '_session_pins', previous)
        with patch.object(timing, 'GLOBAL_TIMELINE_BAR_WIDGETS', [bar]):
            ui.save_toolbar_pins(['history_timeline'])
        self.assertTrue(bar._workflow_buttons['toolkit_bar'].isHidden())
        self.assertFalse(bar._workflow_buttons['history_timeline'].isHidden())
        bar.deleteLater()


if __name__ == '__main__':
    unittest.main()
