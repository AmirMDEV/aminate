"""Teacher-demo selection must include sibling geometry without extra rigs."""
import ast
import math
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TeacherDemoRootTests(unittest.TestCase):
    def setUp(self):
        self.types = {
            '|scene': 'transform', '|scene|Amanda': 'transform',
            '|scene|Amanda|main_control': 'transform',
            '|scene|Amanda|main_control|curve': 'nurbsCurve',
            '|scene|Amanda|no_transform': 'transform',
            '|scene|Amanda|no_transform|mesh': 'mesh',
            '|scene|Amanda|no_transform|joint': 'joint',
            '|scene|Other': 'transform', '|scene|Other|mesh': 'mesh',
            '|scene|Other|joint': 'joint', '|orphan': 'transform',
            '|orphan|curve': 'nurbsCurve', '|prop': 'transform', '|prop|mesh': 'mesh',
        }
        self.links = [('|scene|Amanda|main_control.translateX',
                       '|scene|Amanda|no_transform|joint.translateX')]
        def relatives(node, allDescendents=False, parent=False, children=False, type=None, **kwargs):
            if parent:
                value = node.rsplit('|', 1)[0]
                return [value] if value else []
            return [n for n, kind in self.types.items()
                    if n.startswith(node + '|') and (not children or n.count('|') == node.count('|') + 1)
                    and (type is None or kind == type)]
        def connections(nodes, type=None, **kwargs):
            if type != 'transform':
                return []
            result = []
            for left, right in self.links:
                if left.split('.')[0] in nodes:
                    result += [left, right]
                elif right.split('.')[0] in nodes:
                    result += [right, left]
            return result
        tree = ast.parse((ROOT / 'maya_timing_tools.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == '_teacher_demo_rig_root')
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                      and n.name == 'duplicate_selected_rig_for_teacher_demo')
        self.copied = []
        self.selected = []
        self.ns = dict(cmds=SimpleNamespace(listRelatives=relatives, listConnections=connections,
                                          getAttr=lambda *a, **kw:'double'), _long_scene_name=lambda n:n,
                       MAYA_AVAILABLE=True, DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X=100,
                       _selected_transform_roots=lambda:self.selected,
                       _dedupe_preserve_order=lambda values:list(dict.fromkeys(values)),
                       _duplicate_rig_root_for_teacher_demo=lambda root,**kwargs:
                       (self.copied.append(root) or True, 'Copied', {'source_root':root}))
        exec(compile(ast.Module(body=[function, method], type_ignores=[]), 'teacher_demo', 'exec'), self.ns)
        self.controller = SimpleNamespace(_emit_status=lambda *args:None,
                                          reset_teacher_demo_edit_log=lambda:None)

    def test_control_uses_character_with_sibling_geometry(self):
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|scene|Amanda|main_control'), '|scene|Amanda')

    def test_mesh_selection_uses_complete_character(self):
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|scene|Amanda|no_transform'),
                         '|scene|Amanda')

    def test_control_beside_unrelated_character_is_rejected(self):
        self.types['|scene|orphan'] = 'transform'
        self.types['|scene|orphan|curve'] = 'nurbsCurve'
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|scene|orphan'), '')

    def test_disjoint_connected_assemblies_are_rejected(self):
        self.links.append(('|scene|Amanda|main_control.translateY', '|prop.translateY'))
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|scene|Amanda|main_control'), '')

    def test_expansion_cannot_absorb_unconnected_geometry(self):
        self.links.append(('|scene|Amanda|main_control.translateY', '|scene.translateY'))
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|scene|Amanda|main_control'), '')

    def test_two_controls_in_one_rig_duplicate_once(self):
        self.selected = ['|scene|Amanda|main_control', '|scene|Amanda']
        self.assertTrue(self.ns['duplicate_selected_rig_for_teacher_demo'](self.controller)[0])
        self.assertEqual(self.copied, ['|scene|Amanda'])

    def test_two_characters_are_rejected(self):
        self.selected = ['|scene|Amanda|main_control', '|scene|Other']
        self.assertFalse(self.ns['duplicate_selected_rig_for_teacher_demo'](self.controller)[0])
        self.assertEqual(self.copied, [])

    def test_control_only_branch_is_rejected(self):
        self.selected = ['|orphan']
        self.assertFalse(self.ns['duplicate_selected_rig_for_teacher_demo'](self.controller)[0])
        self.assertEqual(self.copied, [])

    def test_explicit_static_prop_is_supported(self):
        self.assertEqual(self.ns['_teacher_demo_rig_root']('|prop'), '|prop')


def source_functions(*names):
    tree = ast.parse((ROOT / 'maya_timing_tools.py').read_text(encoding='utf-8'))
    return [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]


class TeacherDuplicateHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.types = {
            '|source': 'transform', '|source|rig:control': 'transform',
            '|source|rig:control|rig:curveShape': 'nurbsCurve',
            '|source|rig:geometry': 'transform',
            '|source|rig:geometry|rig:meshOrig': 'mesh',
            '|source|rig:geometry|rig:meshShape': 'mesh',
            '|copy': 'transform', '|copy|geometry': 'transform',
            '|copy|geometry|meshShape101': 'mesh',
            '|copy|geometry|meshShape102': 'mesh',
            '|copy|control': 'transform', '|copy|control|curveShape77': 'nurbsCurve',
        }
        self.children = {
            '|source': ['|source|rig:control', '|source|rig:geometry'],
            '|source|rig:control': ['|source|rig:control|rig:curveShape'],
            '|source|rig:geometry': ['|source|rig:geometry|rig:meshOrig', '|source|rig:geometry|rig:meshShape'],
            '|copy': ['|copy|geometry', '|copy|control'],
            '|copy|geometry': ['|copy|geometry|meshShape101', '|copy|geometry|meshShape102'],
            '|copy|control': ['|copy|control|curveShape77'],
        }
        self.intermediate = {'|source|rig:geometry|rig:meshOrig': True,
                             '|copy|geometry|meshShape101': True}
        self.cmds = SimpleNamespace(
            nodeType=lambda node: self.types[node],
            listRelatives=lambda node, **kwargs: self.children.get(node, []),
            objectType=lambda node, **kwargs: self.types[node] in ('transform', 'joint'),
            getAttr=lambda plug: self.intermediate.get(plug.rsplit('.', 1)[0], False))
        namespace = dict(cmds=self.cmds, _long_scene_name=lambda node: node)
        functions = source_functions('_node_short_name', '_node_base_name', '_teacher_duplicate_hierarchy_pairs')
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'teacher_hierarchy', 'exec'), namespace)
        self.pairs = namespace['_teacher_duplicate_hierarchy_pairs']

    def test_reordered_transform_branches_match_namespace_free_base_names(self):
        pairs = self.pairs('|source', '|copy')
        self.assertIn(('|source|rig:control', '|copy|control'), pairs)
        self.assertIn(('|source|rig:geometry', '|copy|geometry'), pairs)
        self.assertNotIn(('|source|rig:control', '|copy|geometry'), pairs)
        self.assertEqual(len(pairs), 5)

    def test_auto_renamed_shapes_match_within_parent_with_type_and_intermediate_state(self):
        pairs = self.pairs('|source', '|copy')
        self.assertFalse(any('meshOrig' in source or 'meshShape101' in target for source, target in pairs))
        self.assertIn(('|source|rig:geometry|rig:meshShape', '|copy|geometry|meshShape102'), pairs)
        self.assertIn(('|source|rig:control|rig:curveShape', '|copy|control|curveShape77'), pairs)
        for source, target in pairs:
            self.assertEqual(self.types[source], self.types[target])
            self.assertEqual(self.intermediate.get(source, False), self.intermediate.get(target, False))

    def test_nurbs_underworld_paths_are_ignored(self):
        source_surface = '|source|rig:control|rig:curveShape'
        target_surface = '|copy|control|curveShape77'
        self.types[source_surface] = self.types[target_surface] = 'nurbsSurface'
        self.children[source_surface] = [source_surface + '->|underworldTransform']
        self.children[target_surface] = [target_surface + '->|renamedUnderworldTransform']
        pairs = self.pairs('|source', '|copy')
        self.assertEqual(len(pairs), 5)
        self.assertFalse(any('->' in source or '->' in target for source, target in pairs))

    def test_missing_transform_is_rejected(self):
        self.children['|copy'].remove('|copy|control')
        with self.assertRaisesRegex(RuntimeError, 'different transform children'):
            self.pairs('|source', '|copy')

    def test_equal_transform_count_with_unmatched_name_is_rejected(self):
        self.children['|copy'][1] = '|copy|unexpected'
        self.types['|copy|unexpected'] = 'transform'
        with self.assertRaisesRegex(RuntimeError, 'Could not match a duplicated rig transform'):
            self.pairs('|source', '|copy')

    def test_ambiguous_namespace_free_target_names_are_rejected(self):
        self.children['|copy'].append('|copy|other:control')
        self.types['|copy|other:control'] = 'transform'
        with self.assertRaisesRegex(RuntimeError, 'ambiguous child names'):
            self.pairs('|source', '|copy')

    def test_transform_node_type_mismatch_is_rejected(self):
        self.types['|copy|control'] = 'joint'
        with self.assertRaisesRegex(RuntimeError, 'different node type'):
            self.pairs('|source', '|copy')

    def test_shape_node_type_mismatch_is_rejected(self):
        self.types['|copy|control|curveShape77'] = 'mesh'
        with self.assertRaisesRegex(RuntimeError, 'ambiguous or mismatched visible shapes'):
            self.pairs('|source', '|copy')

    def test_intermediate_shape_mismatch_is_rejected(self):
        self.intermediate['|copy|geometry|meshShape101'] = False
        with self.assertRaisesRegex(RuntimeError, 'missing a shape'):
            self.pairs('|source', '|copy')

    def test_missing_shape_is_rejected(self):
        self.children['|copy|geometry'].pop()
        with self.assertRaisesRegex(RuntimeError, 'missing a shape'):
            self.pairs('|source', '|copy')

    def test_reordered_visible_meshes_match_names_instead_of_child_order(self):
        source = '|source|rig:geometry|rig:meshOrig'
        target = '|copy|geometry|meshShape101'
        self.intermediate[source] = self.intermediate[target] = False
        renamed = '|copy|geometry|meshOrig'
        self.types[renamed] = self.types.pop(target)
        self.children['|copy|geometry'] = ['|copy|geometry|meshShape102', renamed]
        pairs = self.pairs('|source', '|copy')
        self.assertIn((source, renamed), pairs)
        self.assertIn(('|source|rig:geometry|rig:meshShape', '|copy|geometry|meshShape102'), pairs)

    def test_ambiguous_auto_renamed_visible_meshes_reject_instead_of_guessing(self):
        self.intermediate['|source|rig:geometry|rig:meshOrig'] = False
        self.intermediate['|copy|geometry|meshShape101'] = False
        with self.assertRaisesRegex(RuntimeError, 'ambiguous or mismatched visible shapes'):
            self.pairs('|source', '|copy')

    def test_extra_intermediate_construction_shape_is_ignored(self):
        extra = '|copy|geometry|meshOrig999'
        self.types[extra] = 'mesh'
        self.intermediate[extra] = True
        self.children['|copy|geometry'].append(extra)
        self.assertEqual(len(self.pairs('|source', '|copy')), 5)

    def test_auto_renamed_curves_match_cv_signature(self):
        source = '|source|rig:control|rig:curveShape2'
        target = '|copy|control|curveShape88'
        self.types[source] = self.types[target] = 'nurbsCurve'
        self.children['|source|rig:control'].append(source)
        self.children['|copy|control'].insert(0, target)
        self.cmds.xform = lambda component, **kwargs: [0, 1, 0] if component.startswith((source, target)) else [0, 0, 0]
        pairs = self.pairs('|source', '|copy')
        self.assertIn((source, target), pairs)
        self.assertIn(('|source|rig:control|rig:curveShape', '|copy|control|curveShape77'), pairs)

    def test_identical_ambiguous_curves_keep_native_copied_state(self):
        source = '|source|rig:control|rig:curveShape2'
        target = '|copy|control|curveShape88'
        self.types[source] = self.types[target] = 'nurbsCurve'
        self.children['|source|rig:control'].append(source)
        self.children['|copy|control'].append(target)
        self.cmds.xform = lambda *args, **kwargs: [0, 0, 0]
        pairs = self.pairs('|source', '|copy')
        self.assertFalse(any(self.types[node] == 'nurbsCurve' for node, _ in pairs))
        self.assertIn(('|source|rig:control', '|copy|control'), pairs)


class TeacherDuplicateOffsetTests(unittest.TestCase):
    def setUp(self):
        self.root = '|source'
        self.copy = '|offset|copy'
        self.group = '|offset'
        self.controls = ['|source|global', '|source|secondary']
        self.meshes = ['|source|meshA', '|source|meshB']
        self.pairs = [(self.root, self.copy)] + [(node, self.copy + node[len(self.root):])
                                                for node in self.controls + self.meshes]
        self.mapping = dict(self.pairs)
        self.values = {self.group + '.translateX': 0.0}
        for _source, target in self.pairs:
            self.values[target + '.inheritsTransform'] = True
            self.values[target + '.translateX'] = 0.0
        self.keys = {}
        self.control_gain = {node: 1.0 for node in self.controls}
        self.group_gain = 1.0
        self.connections = set()
        self.set_calls = []
        self.key_edits = []
        self.samples_read = []
        self.isolated = 0
        self.corrupt_sample = None
        self.cmds = SimpleNamespace(
            listRelatives=self.relatives, ls=lambda values, **kwargs: list(values),
            getAttr=self.get_attr, objectType=lambda node, **kwargs: node not in self.meshes,
            polyEvaluate=lambda node, **kwargs: 3, xform=self.xform,
            listConnections=lambda plug, **kwargs: ['drivingNode'] if plug in self.connections else [],
            keyframe=self.keyframe, setAttr=self.set_attr)

        class Vector(tuple):
            def __new__(cls, *values):
                return tuple.__new__(cls, values)

            def __mul__(self, matrix):
                return self  # Identity parent matrix is sufficient for world-X cases.

        maya = ModuleType('maya')
        api = ModuleType('maya.api')
        api.OpenMaya = SimpleNamespace(MMatrix=lambda value: value, MVector=Vector)
        maya.api = api
        modules = patch.dict(sys.modules, {'maya': maya, 'maya.api': api})
        modules.start()
        self.addCleanup(modules.stop)
        namespace = dict(cmds=self.cmds, math=math,
                         _dedupe_preserve_order=lambda values: list(dict.fromkeys(values)),
                         _disable_skinned_geometry_inherits_transform=self.isolate)
        functions = source_functions('_offset_teacher_duplicate')
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'teacher_offset', 'exec'), namespace)
        self.offset = namespace['_offset_teacher_duplicate']

    def relatives(self, node, allDescendents=False, shapes=False, parent=False, **kwargs):
        if allDescendents:
            return self.meshes
        if shapes:
            return [node + '|curveShape'] if node in self.controls else []
        if parent:
            result = node.rsplit('|', 1)[0]
            return [result] if result else []
        return []

    def get_attr(self, plug, lock=False):
        if lock or plug.endswith('.intermediateObject'):
            return False
        if plug.endswith('.parentInverseMatrix[0]'):
            return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        return self.values[plug]

    def set_attr(self, plug, value):
        self.set_calls.append((plug, value))
        self.values[plug] = value

    def keyframe(self, plug, query=False, valueChange=None, **kwargs):
        if query:
            return len(self.keys.get(plug, []))
        self.key_edits.append((plug, valueChange, kwargs))
        self.keys[plug] = [value + valueChange for value in self.keys[plug]]

    def isolate(self, root):
        self.isolated += 1
        self.values[root + '.inheritsTransform'] = False
        return 1

    def xform(self, component, **kwargs):
        self.samples_read.append(component)
        node, index = component.split('.vtx[')
        index = int(index[:-1])
        source = next((first for first, second in self.pairs if second == node), node)
        mesh_index = self.meshes.index(source)
        point = [float(index + 10 * mesh_index), float(index), float(mesh_index)]
        if node != source:
            shift = self.values[self.group + '.translateX'] * self.group_gain
            for control in self.controls:
                plug = self.mapping[control] + '.translateX'
                value = self.keys[plug][1] if plug in self.keys else self.values[plug]
                shift += value * self.control_gain[control]
            point[0] += shift
            if component == self.corrupt_sample and abs(shift) > 0:
                point[1] += 1.0
        return point

    def run_offset(self, preferred=None):
        return self.offset(self.root, self.group, self.pairs, 100.0, preferred_control=preferred)

    def test_preferred_global_control_is_validated_against_every_visible_mesh_sample(self):
        result = self.run_offset(self.controls[0])
        self.assertEqual(result['offset_mode'], 'global_control')
        self.assertEqual(result['offset_control'], self.mapping[self.controls[0]])
        self.assertEqual(result['verified_mesh_samples'], 6)
        for mesh in self.meshes:
            for index in (0, 1, 2):
                self.assertIn(self.mapping[mesh] + '.vtx[{0}]'.format(index), self.samples_read)
        self.assertEqual(self.values[self.group + '.translateX'], 0.0)

    def test_rejected_candidate_translation_is_restored_before_next_control(self):
        self.control_gain[self.controls[0]] = 0.0
        first_plug = self.mapping[self.controls[0]] + '.translateX'
        result = self.run_offset(self.controls[0])
        self.assertEqual(result['offset_control'], self.mapping[self.controls[1]])
        self.assertEqual(self.values[first_plug], 0.0)
        self.assertIn((first_plug, 100.0), self.set_calls)
        self.assertIn((first_plug, 0.0), self.set_calls)

    def test_existing_animation_keys_use_relative_offset_without_set_attr(self):
        plug = self.mapping[self.controls[0]] + '.translateX'
        self.keys[plug] = [-2.0, 0.0, 4.0]
        result = self.run_offset(self.controls[0])
        self.assertEqual(result['offset_mode'], 'global_control')
        self.assertEqual(self.keys[plug], [98.0, 100.0, 104.0])
        self.assertFalse(any(name == plug for name, _ in self.set_calls))
        self.assertEqual(self.key_edits, [(plug, 100.0, {'edit': True, 'relative': True})])

    def test_rejected_keyed_candidate_restores_animation_keys(self):
        plug = self.mapping[self.controls[0]] + '.translateX'
        self.keys[plug] = [-2.0, 0.0, 4.0]
        self.control_gain[self.controls[0]] = 0.0
        result = self.run_offset(self.controls[0])
        self.assertEqual(result['offset_control'], self.mapping[self.controls[1]])
        self.assertEqual(self.keys[plug], [-2.0, 0.0, 4.0])
        self.assertEqual([amount for name, amount, _ in self.key_edits if name == plug], [100.0, -100.0])
        self.assertFalse(any(name == plug for name, _ in self.set_calls))

    def test_static_prop_uses_validated_group_fallback(self):
        self.control_gain = {node: 0.0 for node in self.controls}
        result = self.run_offset()
        self.assertEqual(result['offset_mode'], 'group')
        self.assertEqual(result['verified_mesh_samples'], 6)
        self.assertEqual(result['disabled_skin_geometry_inherits'], 0)
        self.assertEqual(self.values[self.group + '.translateX'], 100.0)

    def test_distorted_group_rejects_and_restores_inheritance_and_candidate_edits(self):
        self.control_gain = {node: 0.0 for node in self.controls}
        self.group_gain = 2.0
        original = dict(self.values)
        with self.assertRaisesRegex(RuntimeError, 'distorted copy was rejected'):
            self.run_offset()
        self.assertEqual(self.values, original)
        self.assertEqual(self.isolated, 1)

    def test_driven_parent_rotation_scale_shear_or_offset_matrix_excludes_control(self):
        for attr in ('rotate', 'scale', 'shear', 'offsetParentMatrix'):
            with self.subTest(incoming=attr):
                self.connections = {self.copy + '.' + attr}
                self.set_calls.clear()
                self.values[self.group + '.translateX'] = 0.0
                result = self.run_offset()
                self.assertEqual(result['offset_mode'], 'group')
                driver_plugs = {self.mapping[node] + '.translateX' for node in self.controls}
                self.assertFalse(any(plug in driver_plugs for plug, _ in self.set_calls))

    def test_one_distorted_visible_mesh_sample_cannot_pass(self):
        self.corrupt_sample = self.mapping[self.meshes[1]] + '.vtx[1]'
        with self.assertRaisesRegex(RuntimeError, 'distorted copy was rejected'):
            self.run_offset()
        self.assertEqual(self.values[self.group + '.translateX'], 0.0)
        for control in self.controls:
            self.assertEqual(self.values[self.mapping[control] + '.translateX'], 0.0)


class TeacherDuplicateFailureCleanupTests(unittest.TestCase):
    def test_hierarchy_failure_deletes_only_new_uuid_nodes_including_upstream_dg(self):
        original = {'original-source': '|source', 'original-unrelated': '|unrelated',
                    'original-dg': 'existingSkinCluster'}
        nodes = dict(original)
        deleted = []
        undo_calls = []
        uuid_queries = []

        def duplicate(*args, **kwargs):
            nodes.update({'new-root': '|copy', 'new-upstream': 'newSkinCluster',
                          'new-shape': '|copy|meshShape'})
            return ['|copy']

        def ls(values=None, uuid=False, **kwargs):
            if uuid:
                uuid_queries.append(values)
                # Maya's no-argument call returns names, not UUID identity.
                if values is None:
                    return list(nodes.values())
                return [uid for uid, node in nodes.items() if node in values]
            if values is None:
                return list(nodes.values())
            return [nodes[value] for value in values if value in nodes]

        def delete(values):
            deleted.extend(values)
            for uid, node in list(nodes.items()):
                if node in values:
                    del nodes[uid]

        def reject_hierarchy(*args):
            raise RuntimeError('injected hierarchy mismatch')

        namespace = dict(
            DEFAULT_TEACHER_RIG_DUPLICATE_OFFSET_X=100,
            _long_scene_name=lambda node: node,
            _node_base_name=lambda node: node.rsplit('|', 1)[-1],
            _safe_scene_node_name=lambda value, fallback: value,
            _teacher_duplicate_hierarchy_pairs=reject_hierarchy,
            cmds=SimpleNamespace(ls=ls, duplicate=duplicate, delete=delete,
                                 undoInfo=lambda **kwargs: undo_calls.append(kwargs),
                                 listRelatives=lambda node, **kwargs: [node + '|meshShape']))
        functions = source_functions('_duplicate_rig_root_for_teacher_demo')
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'teacher_cleanup', 'exec'), namespace)
        success, message, detail = namespace['_duplicate_rig_root_for_teacher_demo']('|source')
        self.assertFalse(success)
        self.assertIn('injected hierarchy mismatch', message)
        self.assertEqual(detail, {})
        self.assertEqual(set(deleted), {'|copy', 'newSkinCluster', '|copy|meshShape'})
        self.assertEqual(nodes, original)
        self.assertEqual(len(uuid_queries), 2)
        self.assertTrue(all(values is not None for values in uuid_queries))
        self.assertEqual(set(uuid_queries[0]), set(original.values()))
        self.assertTrue(undo_calls[-1].get('closeChunk'))


if __name__ == '__main__':
    unittest.main()
