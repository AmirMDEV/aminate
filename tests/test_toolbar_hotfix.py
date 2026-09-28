"""Headless routing/regression checks; these do not replace live Maya QA."""
import ast
import pathlib
import sys
import tempfile
import types
import unittest
import zipfile
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maya_timing_tools as timing
import maya_reference_manager as reference
import maya_aminate_icon_manifest as icons


def method(filename, cls, name):
    tree = ast.parse((ROOT / filename).read_text())
    owner = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls)
    node = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)
    return namespace[name], namespace


class ToolbarTests(unittest.TestCase):
    def test_every_action_routes_to_expected_operation(self):
        expected = {
            'nudge_left': ('nudge_keys', (-1,)), 'nudge_right': ('nudge_keys', (1,)),
            'insert_inbetween': ('insert_inbetween_key', ()), 'remove_current': ('remove_current_keys', ()),
            'reset_pose': ('reset_selected_transforms', ()), 'bake_twos': ('bake_selected_interval', (2,)),
            'select_animated': ('select_animated_controls', ()), 'clean_static': ('remove_static_animation_curves', ()),
            'combine_freeze_pivot': ('combine_selected_meshes_freeze_edit_pivot', ()),
            'package_scene_zip': ('package_scene_to_zip_from_bar', ()),
            'playblast_1080p': ('playblast_documents_1080p', ()),
            'export_selected_animation_fbx': ('export_selected_animation_fbx_from_bar', ()),
        }
        self.assertEqual({x['command'] for x in icons.ACTION_ICON_MANIFEST}, set(expected) | {'tween_machine', 'game_animation_mode'})
        for command, (name, args) in expected.items():
            with self.subTest(command=command):
                controller = Mock()
                getattr(controller, name).return_value = (True, command)
                self.assertEqual(timing.MayaTimingToolsController.run_student_core_command(controller, command), (True, command))
                getattr(controller, name).assert_called_once_with(*args)

    def test_workflow_buttons_resolve_all_23_tabs(self):
        tree = ast.parse((ROOT / 'maya_dynamic_parent_pivot.py').read_text())
        labels = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith('TAB_') for t in n.targets) and isinstance(n.value, ast.Constant)]
        find, _ = method('maya_dynamic_parent_pivot.py', 'AminateWindow', '_find_tab_index')
        key, _ = method('maya_dynamic_parent_pivot.py', 'AminateWindow', '_tab_key')
        widget = types.SimpleNamespace(count=lambda: len(labels), tabText=lambda i: labels[i])
        owner = types.SimpleNamespace(tab_widget=widget, _tab_key=key)
        self.assertEqual(len(icons.WORKFLOW_ICON_MANIFEST), 23)
        for tool in icons.WORKFLOW_ICON_MANIFEST:
            with self.subTest(tab=tool['tab']):
                self.assertIsNotNone(find(owner, tool['tab']))

    def test_all_toolbar_surfaces_dispatch_package_and_popups(self):
        tree = ast.parse((ROOT / 'maya_timing_tools.py').read_text())
        owners = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and any(isinstance(m, ast.FunctionDef) and m.name == '_run' for m in n.body)]
        self.assertEqual(len(owners), 3)
        for cls in owners:
            run, ns = method('maya_timing_tools.py', cls, '_run')
            ns.update(MAYA_AVAILABLE=False, om2=None, _show_tween_machine_popup=Mock())
            controller = Mock()
            controller.run_student_core_command.return_value = (True, 'zip ready')
            controller.export_selected_animation_fbx_from_bar.return_value = (True, 'options')
            owner = types.SimpleNamespace(controller=controller, status_callback=Mock(), _snapshot_after_toolkit_action=Mock())
            run(owner, 'package_scene_zip')
            controller.run_student_core_command.assert_called_once_with('package_scene_zip')
            run(owner, 'tween_machine')
            ns['_show_tween_machine_popup'].assert_called_once()
            run(owner, 'export_selected_animation_fbx')
            controller.export_selected_animation_fbx_from_bar.assert_called_once_with(parent=owner)

    def test_shared_controller_is_injected(self):
        get, ns = method('maya_dynamic_parent_pivot.py', 'AminateController', 'get_timing_controller')
        ns['maya_timing_tools'] = timing
        controller = types.SimpleNamespace()
        shared = reference.ReferencePackageController()
        owner = types.SimpleNamespace(_controller=lambda *args: controller, reference_manager_controller=shared)
        self.assertIs(get(owner).reference_package_controller, shared)

    def test_toolbar_uses_shared_package_state_and_opens_zip_parent(self):
        controller = object.__new__(timing.MayaTimingToolsController)
        shared = Mock()
        shared.package_current_scene.return_value = {'zip_path': '/tmp/shot.zip', 'package_dir': '/tmp/shot', 'missing_count': 0}
        controller.reference_package_controller = shared
        controller.create_history_auto_snapshot = Mock()
        controller._emit_status = Mock()
        with patch.object(timing, 'MAYA_AVAILABLE', True), patch.object(timing.os.path, 'isdir', return_value=True), patch.object(timing.os, 'startfile', create=True) as open_folder:
            self.assertTrue(controller.package_scene_to_zip_from_bar()[0])
            shared.package_current_scene.assert_called_once_with(include_references=True, include_external=True, save_scene=True, retarget_package_scene=True)
            open_folder.assert_called_once_with('/tmp')

    def test_package_result_survives_refresh_and_retains_missing_warning(self):
        run, ns = method('maya_reference_manager.py', 'ReferenceManagerPanel', 'package_scene')
        ns['package_result_message'] = reference.package_result_message
        controller = Mock()
        controller.package_current_scene.return_value = {'zip_path': '/tmp/a.zip', 'missing_count': 2, 'warnings': ['Binary paths unchanged.']}
        value = Mock(); value.text.return_value = '/tmp'; value.isChecked.return_value = True
        owner = types.SimpleNamespace(controller=controller, output_path=value, package_name=value, references_box=value, external_box=value, save_scene_box=value, relative_box=value, _set_status=Mock())
        owner.refresh_files = lambda: owner._set_status('scan complete', True)
        run(owner)
        message, success = owner._set_status.call_args.args
        self.assertFalse(success)
        self.assertIn('/tmp/a.zip', message)
        self.assertIn('Missing 2', message)
        self.assertIn('Binary paths unchanged.', message)

    def test_bake_failure_closes_undo_chunk_once(self):
        cmds = Mock()
        cmds.playbackOptions.side_effect = [1, 24]
        cmds.bakeResults.side_effect = RuntimeError('locked channel')
        with patch.object(timing, 'MAYA_AVAILABLE', True), patch.object(timing, 'cmds', cmds), patch.object(timing, '_selected_transform_nodes', return_value=['ctrl']):
            result = timing.MayaTimingToolsController.bake_selected_interval(object(), 2)
        self.assertFalse(result[0])
        self.assertEqual(sum(c.kwargs.get('closeChunk', False) for c in cmds.undoInfo.call_args_list), 1)

    def test_real_zip_creation_with_mocked_maya_and_shared_last_result(self):
        with tempfile.TemporaryDirectory() as folder:
            scene = pathlib.Path(folder) / 'shot.ma'
            scene.write_text('//Maya ASCII scene\n')
            controller = reference.ReferencePackageController()
            controller.collect_dependencies = Mock(return_value={'records': []})
            with patch.object(reference, 'MAYA_AVAILABLE', True), patch.object(reference, 'cmds', Mock()), patch.object(reference, '_scene_path', return_value=str(scene)), patch.object(reference, '_scene_file_type', return_value=('mayaAscii', '.ma')):
                result = controller.package_current_scene(output_dir=folder, save_scene=True)
            self.assertIs(controller.last_result, result)
            self.assertEqual(reference.package_result_folder(result), folder)
            with zipfile.ZipFile(result['zip_path']) as archive:
                self.assertTrue(any(name.endswith('/scenes/shot_packaged.ma') for name in archive.namelist()))
                self.assertTrue(any(name.endswith('/reference_package_manifest.json') for name in archive.namelist()))


if __name__ == '__main__':
    unittest.main()
