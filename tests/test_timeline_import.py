"""Ordinary-Python Timeline Notes regression using real methods and mocked Maya.

Extract the controller and its data helpers so no Maya or Qt modules load.
"""
import ast
import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "maya_timeline_notes.py"


def load_controller():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    helpers = {
        "_blend_channel", "_blend_color", "_set_string_attr", "_set_bool_attr",
        "_set_double_attr", "_get_string_attr", "_get_bool_attr", "_get_double_attr",
        "_bookmark_nodes", "_note_payload",
    }
    nodes = []
    namespace = {"json": json, "MAYA_AVAILABLE": True,
                 "_has_playback_slider": lambda: True, "_short_name": lambda node: node}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith(("NOTE_", "DEFAULT_")):
                    try:
                        namespace[target.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
        elif isinstance(node, ast.FunctionDef) and node.name in helpers:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "MayaTimelineNotesController":
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class TimelineImportTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_controller()
        self.scene = {}
        self.cmds = Mock()
        self.cmds.objExists.side_effect = lambda node: node in self.scene
        self.cmds.attributeQuery.side_effect = lambda attr, node, exists: attr in self.scene[node]
        self.cmds.addAttr.side_effect = lambda node, longName, **kwargs: self.scene[node].update({longName: None})
        self.cmds.setAttr.side_effect = self.set_attr
        self.cmds.getAttr.side_effect = lambda plug: self.scene[plug.split(".", 1)[0]][plug.split(".", 1)[1]]
        self.namespace["cmds"] = self.cmds
        self.api = Mock()
        self.api.createBookmark.side_effect = self.create_bookmark
        self.api.updateBookmark.side_effect = self.update_bookmark
        self.api.getAllBookmarks.side_effect = lambda: list(self.scene)
        cls = self.namespace["MayaTimelineNotesController"]
        self.controller = object.__new__(cls)
        self.controller.bookmark_api = self.api
        self.controller.overlay_widget = None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file_path = pathlib.Path(self.temp.name) / "notes.json"

    def set_attr(self, plug, *values, **kwargs):
        node, attr = plug.split(".", 1)
        self.scene[node][attr] = values[0] if len(values) == 1 else values

    def create_bookmark(self, name, start, stop, color):
        node = "destinationBookmark{0}".format(len(self.scene) + 1)
        self.scene[node] = {"name": name, "timeRangeStart": start,
                            "timeRangeStop": stop, "color": color}
        return node

    def update_bookmark(self, node, start, stop):
        self.scene[node].update(timeRangeStart=start, timeRangeStop=stop)

    def incoming(self, **changes):
        note = dict(title="Source note", start_frame=4, end_frame=9,
                    color=[0.2, 0.4, 0.6], opacity=0.7, text="Original",
                    export_id="sourceBookmark17")
        note.update(changes)
        return note

    def import_items(self, items):
        self.file_path.write_text(json.dumps({"version": 1, "notes": items}), encoding="utf-8")
        return self.controller.import_notes(str(self.file_path))

    def test_repeated_cross_scene_import_updates_and_preserves_export_identity(self):
        self.assertTrue(self.import_items([self.incoming()])[0])
        note = self.controller.notes()[0]
        self.assertNotEqual(note["node"], note["export_id"])
        self.assertEqual(note["export_id"], "sourceBookmark17")
        success, message = self.import_items([self.incoming(title="Revised", text="Changed", start_frame=6)])
        self.assertTrue(success)
        self.assertIn("0 new note(s) and updated 1", message)
        self.assertEqual(len(self.scene), 1)
        note = self.controller.notes()[0]
        self.assertEqual((note["title"], note["text"], note["start_frame"]), ("Revised", "Changed", 6))
        self.controller.export_notes(str(self.file_path))
        self.assertEqual(json.loads(self.file_path.read_text())["notes"][0]["export_id"], "sourceBookmark17")

    def test_duplicate_ids_within_one_file_reuse_created_note(self):
        success, message = self.import_items([self.incoming(), self.incoming(text="Last entry")])
        self.assertTrue(success)
        self.assertIn("1 new note(s) and updated 1", message)
        self.assertEqual(len(self.scene), 1)
        self.assertEqual(self.controller.notes()[0]["text"], "Last entry")

    def test_failed_create_returns_false(self):
        success, message = self.import_items([self.incoming(start_frame=10, end_frame=2)])
        self.assertFalse(success)
        self.assertIn("Failed to import 1 note(s)", message)
        self.assertEqual(self.scene, {})

    def test_failed_update_returns_false(self):
        self.import_items([self.incoming()])
        with patch.object(self.controller, "update_note", return_value=(False, "Unavailable")):
            success, message = self.import_items([self.incoming(text="Cannot update")])
        self.assertFalse(success)
        self.assertIn("updated 0", message)
        self.assertIn("Failed to import 1 note(s)", message)
        self.assertEqual(self.controller.notes()[0]["text"], "Original")

    def test_partial_success_reports_failed_count(self):
        success, message = self.import_items([
            self.incoming(), self.incoming(export_id="invalid", start_frame=10, end_frame=2)])
        self.assertTrue(success)
        self.assertIn("1 new note(s)", message)
        self.assertIn("Failed to import 1 note(s)", message)
        self.assertEqual(len(self.scene), 1)

    def test_empty_import_does_not_report_success(self):
        self.assertFalse(self.import_items([])[0])

    def test_creation_without_export_identity_keeps_local_identity(self):
        success, _ = self.controller.create_note("Local", 1, 2, (0.2, 0.4, 0.6), 0.7, "Text")
        self.assertTrue(success)
        note = self.controller.notes()[0]
        self.assertEqual(note["export_id"], note["node"])


if __name__ == "__main__":
    unittest.main()
