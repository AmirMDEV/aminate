"""Behaviour regressions for the second toolbar audit."""
import sys
import types
import unittest
from unittest.mock import Mock, patch, call
from test_toolbar_hotfix import method, timing, icons


class FollowupTests(unittest.TestCase):
    def test_no_selection_never_falls_back_to_scene(self):
        controller = object.__new__(timing.MayaTimingToolsController)
        controller._student_core_targets = lambda: timing.MayaTimingToolsController._student_core_targets(controller)
        cmds = Mock(); cmds.keyframe.return_value = []
        with patch.object(timing, 'MAYA_AVAILABLE', True), patch.object(timing, 'cmds', cmds), patch.object(timing, '_selected_transform_nodes', return_value=[]), patch.object(timing, '_scene_keyed_transforms') as scene:
            for action in (lambda: controller.nudge_keys(-1), controller.insert_inbetween_key, controller.remove_current_keys):
                self.assertFalse(action()[0])
            scene.assert_not_called()
            cmds.setKeyframe.assert_not_called(); cmds.cutKey.assert_not_called(); cmds.undoInfo.assert_not_called()
            self.assertTrue(all(c.kwargs.get('query') for c in cmds.keyframe.call_args_list))

    def test_graph_editor_key_selection_still_nudges(self):
        cmds = Mock(); cmds.keyframe.return_value = ['curve']
        with patch.object(timing, 'MAYA_AVAILABLE', True), patch.object(timing, 'cmds', cmds):
            self.assertTrue(timing.MayaTimingToolsController.nudge_keys(object(), 1)[0])
        cmds.keyframe.assert_any_call(edit=True, selected=True, relative=True, timeChange=1)

    def test_both_toolbar_package_buttons_use_zip_action(self):
        run, _ = method('maya_timing_tools.py', 'StudentTimelineButtonBarWindow', '_run_workflow_button')
        owner = types.SimpleNamespace(_run=Mock(), _open_workflow_tab=Mock())
        run(owner, 'reference_manager')
        owner._run.assert_called_once_with('package_scene_zip')
        owner._open_workflow_tab.assert_not_called()
        run(owner, 'control_picker')
        owner._open_workflow_tab.assert_called_once_with('control_picker')

    def test_layer_graph_finds_controls_without_crossing_rig_graph(self):
        graph = {'curve.output': ['mix.inputA'], 'direct.output': ['plain.tx'], 'mix': ['convert.input', 'mix.inputB'], 'convert': ['layered.tx']}
        kinds = {'mix': 'animBlendNodeAdditiveDL', 'convert': 'unitConversion', 'plain': 'transform', 'layered': 'transform'}
        cmds = Mock(); cmds.ls.return_value = ['curve', 'direct']
        cmds.listConnections.side_effect = lambda item, **kw: graph.get(item, [])
        cmds.nodeType.side_effect = kinds.__getitem__
        with patch.object(timing, 'cmds', cmds):
            self.assertEqual(set(timing._scene_keyed_transforms()), {'plain', 'layered'})
        self.assertLess(len(cmds.listConnections.call_args_list), 6)

    def test_static_api_predicate_and_fail_closed(self):
        api = Mock(); api.MFnAnimCurve.return_value = types.SimpleNamespace(numKeys=2, isStatic=False)
        with patch.object(timing, 'om2', Mock()), patch.object(timing, 'oma2', api):
            self.assertFalse(timing._is_proven_static_curve('curvedBetweenEqualKeys'))
            api.MFnAnimCurve.return_value.isStatic = True
            self.assertTrue(timing._is_proven_static_curve('flat'))
        with patch.object(timing, 'oma2', None):
            self.assertFalse(timing._is_proven_static_curve('unverifiable'))

    def clean_commands(self):
        cmds = Mock()
        cmds.referenceQuery.return_value = False
        cmds.lockNode.return_value = [False]
        cmds.listConnections.return_value = ['ctrl.tx']
        cmds.ls.return_value = ['|rig|ctrl']
        cmds.getAttr.side_effect = lambda plug, **kw: False if kw.get('lock') else 12.5
        return cmds

    def test_cleanup_preserves_value_before_deleting(self):
        cmds = self.clean_commands()
        with patch.object(timing, 'cmds', cmds), patch.object(timing, '_is_proven_static_curve', return_value=True):
            self.assertTrue(timing._remove_static_curve_preserving_value('curve', ['ctrl']))
        edits = [c for c in cmds.mock_calls if c[0] in ('disconnectAttr', 'setAttr', 'delete')]
        self.assertEqual(edits, [call.disconnectAttr('curve.output', 'ctrl.tx'), call.setAttr('ctrl.tx', 12.5), call.delete('curve')])

    def test_cleanup_reconnects_if_value_cannot_be_preserved(self):
        cmds = self.clean_commands(); cmds.setAttr.side_effect = RuntimeError('locked')
        with patch.object(timing, 'cmds', cmds), patch.object(timing, '_is_proven_static_curve', return_value=True):
            self.assertFalse(timing._remove_static_curve_preserving_value('curve', ['ctrl']))
        cmds.delete.assert_not_called()
        cmds.connectAttr.assert_called_once_with('curve.output', 'ctrl.tx', force=True)

    def test_cleanup_skips_shared_or_unselected_destinations(self):
        for destinations, target_paths in [(['ctrl.tx', 'other.tx'], ['|rig|ctrl']), (['other.tx'], ['|rig|other'])]:
            cmds = self.clean_commands(); cmds.listConnections.return_value = destinations
            cmds.ls.side_effect = lambda node, **kw: ['|rig|ctrl'] if isinstance(node, list) else target_paths
            with patch.object(timing, 'cmds', cmds), patch.object(timing, '_is_proven_static_curve', return_value=True):
                self.assertFalse(timing._remove_static_curve_preserving_value('curve', ['ctrl']))
            cmds.disconnectAttr.assert_not_called(); cmds.delete.assert_not_called()

    def test_failed_tab_build_returns_false_and_visible_status(self):
        build, ns = method('maya_dynamic_parent_pivot.py', 'AminateWindow', '_ensure_tab_content')
        ns.update(_warning=Mock(), _apply_aminate_combo_affordances=Mock())
        tabs = Mock(); tabs.count.return_value = 1; tabs.tabText.return_value = 'Broken'
        owner = types.SimpleNamespace(tab_widget=tabs, _built_tab_names=set(), _tab_builders={'Broken': Mock(side_effect=RuntimeError('missing dependency'))}, _set_status=Mock())
        self.assertFalse(build(owner, 0))
        self.assertIn('missing dependency', owner._last_tab_error)
        self.assertFalse(owner._set_status.call_args.args[1])
        self.assertFalse(owner._built_tab_names)

    def test_workflow_open_reports_build_show_and_visibility_failures(self):
        for failure in ('build', 'show', 'hidden', 'none'):
            window = Mock(); window._set_initial_tab.return_value = failure != 'build'
            window._last_tab_error = 'cannot build'
            window.isVisible.return_value = failure != 'hidden'
            if failure == 'show': window.show.side_effect = RuntimeError('cannot show')
            with patch.dict(sys.modules, {'maya_dynamic_parent_pivot': types.SimpleNamespace(GLOBAL_WINDOW=window)}), patch.object(timing, 'MAYA_AVAILABLE', True), patch.object(timing, '_qt_object_valid', return_value=True):
                ok, message = timing._open_workflow_tab('control_picker')
            self.assertEqual(ok, failure == 'none')
            if failure != 'none': self.assertNotIn('Opened', message)


if __name__ == '__main__':
    unittest.main()
