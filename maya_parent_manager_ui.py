"""Native Qt panel for Aminate's scene-backed Parent Manager."""

from maya import cmds, mel
from maya.api import OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import maya_parent_manager as engine
from maya_aminate_ui import Disclosure
from maya_timeline_notes import refresh_parent_manager_timeline


_CHANNELS = ("translate", "rotate", "scale")
_ORIGIN = "origin"
_POINT_COLORS = (
    ("Amber", (1.0, 0.66, 0.24)),
    ("Blue", (0.35, 0.68, 1.0)),
    ("Green", (0.45, 0.83, 0.45)),
    ("Pink", (0.94, 0.48, 0.71)),
    ("White", (0.95, 0.95, 0.95)),
)
_TUTORIAL_LESSONS = {
    "handoff": (
        "Pick up and pass a box",
        "1. Select Box. Click Use Selection beside I want. Keep Move and Turn on.\n\n"
        "2. At frame 16, select Left_Hand. Click Use Selection beside to follow, then Start following here.\n\n"
        "3. At frame 40, pick Right_Hand on the same line, then click Follow this instead.\n\n"
        "4. At frame 64, click Stop following and keep this pose. Play from frame 1. The box should pass "
        "between the hands without jumping and stay put after release.\n\n"
        "5. Use Show follow keys and Follow history to inspect the changes. Try moving the handoff "
        "from frame 40 to 41, then undo.\n\n"
        "To practise saving a grip, pick Practice_Crate beside to follow. Select Orange_Top_Grip_Guide "
        "under the crate, click Save a new attach point, and name it Orange top grip.",
    ),
    "attach_points": (
        "Move between attach points",
        "1. Expand Lesson_02_Saved_Spots in the Outliner. Pick Practice_Hand beside I want and "
        "Practice_Crate beside to follow. Keep Move and Turn on. If you need the close-up view, "
        "choose Panels → Perspective → Saved_Spots_Camera in the viewport.\n\n"
        "2. Under Attach To Points, choose Blue side grip. Tick Set start and arrival frames. Set the "
        "start to 9 and arrival to 20, then click Move to attach point and follow.\n\n"
        "3. Scrub from frame 9 to 32. The hand should reach the grip, then rise with the crate. At frame 36, "
        "click Stop following and keep this pose. Scrub to frame 44 to see the hand stay put.\n\n"
        "4. Choose Orange top grip. Turn on Set start and arrival frames again. Set the start to 44 "
        "and arrival to 56, then click Move to attach point and follow. Scrub to frame 69 to see "
        "the hand turn into the top grip and follow the crate.",
    ),
}


def _short(node):
    return node.rsplit("|", 1)[-1] if node else "World"


def _frame_text(value):
    return format(float(value), ".12g")


def _color_icon(rgb):
    swatch = QtGui.QPixmap(12, 12)
    swatch.fill(QtGui.QColor.fromRgbF(*(max(0.0, min(1.0, float(value))) for value in rgb)))
    return QtGui.QIcon(swatch)


def _selected_transform():
    nodes = set()
    for item in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        if cmds.objectType(item, isAType="transform"):
            nodes.add(item)
        elif cmds.objectType(item, isAType="shape"):
            nodes.update(cmds.listRelatives(item, parent=True, fullPath=True) or [])
        else:
            raise ValueError("Select one object or control in the scene.")
    if len(nodes) != 1:
        raise ValueError("Select one object or control in the scene.")
    return nodes.pop()


class ParentManagerPanel(QtWidgets.QWidget):
    """Pick a scene object, then key who it follows at the current frame."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aminateParentManager")
        self.setProperty("aminateEmbeddedPanel", True)
        self._object_id = None
        self._parent_id = None
        self._world = False
        self._object = None
        self._parent = None
        self._active = None
        self._active_known = False
        self._points = []
        self._frame = None
        self._follow_key_plugs = []
        self._build()
        self._frame_timer = QtCore.QTimer(self)
        self._frame_timer.setInterval(120)
        self._frame_timer.timeout.connect(self._poll_frame)
        self._history_refresh = QtCore.QTimer(self)
        self._history_refresh.setSingleShot(True)
        self._history_refresh.timeout.connect(self.refresh)
        callbacks = []

        def refresh_after_undo(*_):
            if self.isVisible():
                self._history_refresh.start(0)

        def remove_callbacks(*_):
            for callback in callbacks:
                om.MMessage.removeCallback(callback)

        self.destroyed.connect(remove_callbacks)
        for event in ("Undo", "Redo"):
            callbacks.append(om.MEventMessage.addEventCallback(event, refresh_after_undo))
        self.refresh()

    @staticmethod
    def _button(text, name, tip):
        button = QtWidgets.QPushButton(text)
        button.setObjectName(name)
        button.setToolTip(tip)
        button.setAutoDefault(False)
        return button

    @staticmethod
    def _label(text=""):
        label = QtWidgets.QLabel(text)
        label.setTextFormat(QtCore.Qt.PlainText)
        label.setWordWrap(True)
        return label

    def _pick_row(self, layout, row, label, purpose, name, callback):
        field = QtWidgets.QLineEdit()
        field.setObjectName(name)
        field.setReadOnly(True)
        field.setAccessibleName(purpose)
        field.setMinimumWidth(0)
        field.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        field.setPlaceholderText(purpose)
        caption = QtWidgets.QLabel(label)
        caption.setBuddy(field)
        pick = self._button("Use Selection", name + "Pick", purpose + " from your Maya selection.")
        pick.setAccessibleName(purpose + " using Maya selection")
        pick.clicked.connect(callback)
        layout.addWidget(caption, row, 0)
        layout.addWidget(field, row, 1, 1, 2 if row == 0 else 1)
        layout.addWidget(pick, row, 3)
        return field

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        tutorial = self._button("Tutorial", "parentManagerTutorial", "Open a practice lesson in a new Maya scene.")
        tutorial_menu = QtWidgets.QMenu(tutorial)
        tutorial_menu.setObjectName("parentManagerTutorialMenu")
        for lesson, (title, _) in _TUTORIAL_LESSONS.items():
            action = tutorial_menu.addAction(title)
            action.setObjectName("parentManagerTutorial_" + lesson)
            action.triggered.connect(lambda checked=False, key=lesson: self._open_tutorial(key))
        tutorial.setMenu(tutorial_menu)
        layout.addWidget(tutorial, alignment=QtCore.Qt.AlignRight)

        picks = QtWidgets.QGridLayout()
        picks.setColumnStretch(1, 1)
        self.object_field = self._pick_row(picks, 0, "I want", "Pick what should move", "parentManagerObject", self._pick_object)
        self.parent_field = self._pick_row(picks, 1, "to follow", "Pick what it should follow", "parentManagerParent", self._pick_parent)
        world = self._button("World", "parentManagerWorld", "Use the scene itself as the thing to follow.")
        world.setAccessibleName("Follow World")
        world.clicked.connect(self._pick_world)
        picks.addWidget(world, 1, 2)

        channels = QtWidgets.QHBoxLayout()
        self.channel_checks = {}
        for name, label in zip(_CHANNELS, ("Move", "Turn", "Resize")):
            check = QtWidgets.QCheckBox(label)
            check.setObjectName("parentManager" + name.title())
            check.setChecked(name != "scale")
            check.setAccessibleName("Follow when the target changes its " + name)
            check.setToolTip("Follow when the target changes its " + name + ".")
            check.toggled.connect(self._sync_controls)
            channels.addWidget(check)
            self.channel_checks[name] = check
        channels.addStretch()
        picks.addLayout(channels, 2, 1, 1, 3)
        layout.addLayout(picks)

        self.point_combo = QtWidgets.QComboBox()
        self.point_combo.setObjectName("parentManagerPoint")
        self.point_combo.setAccessibleName("Attach To Points")
        self.point_combo.setToolTip("Choose a point to preview its marker. Then choose how to follow.")
        self.point_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.point_combo.setMinimumContentsLength(8)
        self.point_combo.currentIndexChanged.connect(self._point_changed)
        self.point_combo.activated.connect(self._preview_point)
        point_label = QtWidgets.QLabel("Attach To Points")
        point_label.setBuddy(self.point_combo)
        point_row = QtWidgets.QHBoxLayout()
        point_row.addWidget(point_label)
        point_row.addWidget(self.point_combo, 1)
        layout.addLayout(point_row)
        self.point_labels = QtWidgets.QCheckBox("Show point names in viewport")
        self.point_labels.setObjectName("parentManagerPointNames")
        self.point_labels.setToolTip("Show names beside the attach points on the chosen follow target.")
        self.point_labels.toggled.connect(self._toggle_point_names)
        layout.addWidget(self.point_labels)

        self.active_label = self._label()
        self.active_label.setObjectName("parentManagerActiveRelationship")
        layout.addWidget(self.active_label)
        self.next_action = self._label()
        self.next_action.setProperty("aminateRole", "muted")
        self.next_action.setObjectName("parentManagerNextAction")
        layout.addWidget(self.next_action)
        self.apply_button = self._button("Start following here", "parentManagerAttach", "Key the follow on this frame.")
        self.apply_button.setProperty("aminateRole", "primary")
        self.apply_button.clicked.connect(self._attach)
        layout.addWidget(self.apply_button)

        self.match_options = QtWidgets.QWidget()
        match_layout = QtWidgets.QGridLayout(self.match_options)
        match_layout.setContentsMargins(0, 0, 0, 0)
        self.timing_toggle = QtWidgets.QCheckBox("Set start and arrival frames")
        self.timing_toggle.setObjectName("parentManagerSetTiming")
        self.timing_toggle.toggled.connect(self._timing_toggled)
        match_layout.addWidget(self.timing_toggle, 0, 0)
        self.timing_fields = QtWidgets.QWidget()
        timing_layout = QtWidgets.QGridLayout(self.timing_fields)
        timing_layout.setContentsMargins(0, 0, 0, 0)
        self.match_start = self._frame_field(timing_layout, 0, "Start moving on", "parentManagerMatchStart")
        self.match_end = self._frame_field(timing_layout, 1, "Reach the point on", "parentManagerMatchEnd")
        match_layout.addWidget(self.timing_fields, 1, 0)
        self.match_help = self._label()
        self.match_help.setProperty("aminateRole", "muted")
        match_layout.addWidget(self.match_help, 2, 0)
        self.match_button = self._button("Move to attach point and follow", "parentManagerAttachAtPoint", "")
        self.match_button.clicked.connect(self._attach_at_point)
        match_layout.addWidget(self.match_button, 3, 0)
        self.match_options.hide()
        layout.addWidget(self.match_options)

        self.detach_button = self._button(
            "Stop following and keep this pose", "parentManagerDetach", "Key the release on this frame and animate freely again."
        )
        self.detach_button.clicked.connect(self._detach)
        layout.addWidget(self.detach_button)

        self.create_point_button = self._button(
            "Save a new attach point", "parentManagerCreatePoint",
            "Select a locator or control where you want the object to go, then click here.",
        )
        self.create_point_button.clicked.connect(self._create_point)
        layout.addWidget(self.create_point_button)
        self.edit_point_button = self._button(
            "Rename or recolour point", "parentManagerEditPoint", "Edit the selected attach point."
        )
        self.edit_point_button.clicked.connect(self._edit_point)
        layout.addWidget(self.edit_point_button)

        self.status = self._label()
        self.status.setObjectName("parentManagerStatus")
        self.status.hide()
        layout.addWidget(self.status)

        self.tutorial_steps = self._label()
        self.tutorial_steps.setObjectName("parentManagerTutorialSteps")
        self.tutorial_guide = Disclosure("Lesson steps")
        self.tutorial_guide.toggle.setObjectName("parentManagerTutorialGuide")
        self.tutorial_guide.toggle.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.tutorial_guide.content.addWidget(self.tutorial_steps)
        self.tutorial_guide.hide()
        layout.addWidget(self.tutorial_guide)

        self.key_summary = self._label()
        self.key_summary.setObjectName("parentManagerKeySummary")
        self.key_summary.setProperty("aminateRole", "muted")
        layout.addWidget(self.key_summary)
        self.key_button = self._button(
            "Show follow keys", "parentManagerSelectKeys",
            "Show each parent's coloured ticks in Maya's Time Slider. Updates older Aminate setups too.",
        )
        self.key_button.clicked.connect(self._select_follow_keys)
        layout.addWidget(self.key_button)

        history_box = QtWidgets.QWidget()
        history_layout = QtWidgets.QVBoxLayout(history_box)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(4)
        self.history_hint = self._label("Pick what should move to see its follow changes.")
        history_layout.addWidget(self.history_hint)
        self.history_list = QtWidgets.QTreeWidget()
        self.history_list.setObjectName("parentManagerHistory")
        self.history_list.setAccessibleName("Follow history. Activate a row to jump to its frame.")
        self.history_list.setHeaderLabels(("Frame", "Follows"))
        self.history_list.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.history_list.header().setSectionsMovable(False)
        self.history_list.setRootIsDecorated(False)
        self.history_list.setUniformRowHeights(True)
        self.history_list.setTextElideMode(QtCore.Qt.ElideRight)
        self.history_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.history_list.setMaximumHeight(146)
        self.history_list.setMinimumHeight(84)
        self.history_list.itemClicked.connect(self._jump_to_frame)
        self.history_list.itemActivated.connect(self._jump_to_frame)
        self.history_list.hide()
        history_layout.addWidget(self.history_list)
        self.history_list.currentItemChanged.connect(self._sync_history_actions)
        self.history_actions = QtWidgets.QWidget()
        actions = QtWidgets.QGridLayout(self.history_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        self.earlier_button = QtWidgets.QPushButton("1 frame earlier")
        self.later_button = QtWidgets.QPushButton("1 frame later")
        for column, (button, offset) in enumerate(((self.earlier_button, -1), (self.later_button, 1))):
            button.setToolTip("Move the selected change, its keys and its timeline bookmarks.")
            button.clicked.connect(lambda checked=False, step=offset: self._nudge_follow_change(step))
            actions.addWidget(button, 0, column)
        self.destination_frame = QtWidgets.QDoubleSpinBox()
        self.destination_frame.setObjectName("parentManagerDestinationFrame")
        self.destination_frame.setAccessibleName("Destination frame")
        self.destination_frame.setDecimals(3)
        self.destination_frame.setRange(-1e8, 1e8)
        self.destination_frame.setKeyboardTracking(False)
        self.destination_frame.setToolTip("For an attach point, enter the frame you want it to arrive on.")
        self.move_button = QtWidgets.QPushButton("Move to frame")
        self.move_button.setObjectName("parentManagerMoveChange")
        self.move_button.clicked.connect(lambda: self._move_follow_change(self.destination_frame.value()))
        actions.addWidget(self.destination_frame, 1, 0)
        actions.addWidget(self.move_button, 1, 1)
        self.remove_button = QtWidgets.QPushButton("Remove change")
        self.remove_button.setObjectName("parentManagerRemoveChange")
        self.remove_button.setToolTip("Remove this follow change, its tick and bookmark. Keep the object's pose keys.")
        self.remove_button.clicked.connect(self._remove_follow_change)
        actions.addWidget(self.remove_button, 2, 0, 1, 2)
        self.release_hint = self._label(
            "This release uses older or edited pose keys. Aminate protects those keys when moving the change."
        )
        self.release_hint.setProperty("aminateRole", "muted")
        actions.addWidget(self.release_hint, 3, 0, 1, 2)
        self._sync_history_actions()
        self.history_actions.hide()
        history_layout.addWidget(self.history_actions)
        self.bookmarks_button = QtWidgets.QPushButton("Update timeline bookmarks")
        self.bookmarks_button.clicked.connect(self._add_bookmarks)
        self.bookmarks_button.hide()
        history_layout.addWidget(self.bookmarks_button)
        self.history_toggle = self._disclosure(layout, "Follow history", history_box)
        self.history_toggle.toggled.connect(self._refresh_history)

    def _open_tutorial(self, lesson):
        title, steps = _TUTORIAL_LESSONS[lesson]
        try:
            from maya_parent_manager_tutorial import build_practice_scene

            if not self._save_before_tutorial(title):
                return
            cmds.file(new=True)
        except Exception as exc:
            self._set_status(f"Could not open the tutorial. {exc}", error=True)
            return

        self._object_id = None
        self._parent_id = None
        self._world = False
        self.tutorial_guide.hide()
        with QtCore.QSignalBlocker(self.point_combo):
            self.point_combo.setCurrentIndex(0)
        with QtCore.QSignalBlocker(self.timing_toggle):
            self.timing_toggle.setChecked(False)
        for name, check in self.channel_checks.items():
            with QtCore.QSignalBlocker(check):
                check.setChecked(name != "scale")
        try:
            build_practice_scene(lesson)
        except Exception as exc:
            self.refresh()
            self._set_status(f"Could not build the tutorial in the new scene. {exc}", error=True)
            return

        self.refresh()
        self._set_status()
        self.tutorial_guide.toggle.setText(title + " steps")
        self.tutorial_guide.toggle.setAccessibleName(title + " steps")
        self.tutorial_steps.setText(steps)
        self.tutorial_guide.setExpanded(True)
        self.tutorial_guide.show()
        if lesson == "attach_points" and not cmds.about(batch=True):
            try:
                self._show_saved_spots_camera()
            except RuntimeError as exc:
                self._set_status(f"Lesson opened. Choose Saved_Spots_Camera in the viewport. {exc}", error=True)

    @staticmethod
    def _show_saved_spots_camera():
        focused = cmds.getPanel(withFocus=True)
        models = set(cmds.getPanel(type="modelPanel") or [])
        visible = cmds.getPanel(visiblePanels=True) or []
        for panel in sorted(visible, key=lambda name: name != focused):
            if panel not in models:
                continue
            camera = cmds.modelPanel(panel, query=True, camera=True)
            if camera and not cmds.camera(camera, query=True, orthographic=True):
                cmds.modelPanel(panel, edit=True, camera="Saved_Spots_Camera")
                break

    @staticmethod
    def _save_before_tutorial(title):
        if not cmds.file(query=True, modified=True):
            return True

        save, cancel = "Save and continue", "Cancel"
        choice = cmds.confirmDialog(
            title="Open Parent Manager Tutorial",
            message=f"“{title}” opens in a new scene. Save your current scene before continuing.",
            button=[save, cancel],
            defaultButton=cancel,
            cancelButton=cancel,
            dismissString=cancel,
        )
        if choice != save:
            return False
        if cmds.file(query=True, sceneName=True):
            cmds.file(save=True)
        elif not mel.eval('projectViewer "SaveAs"'):
            return False
        return not cmds.file(query=True, modified=True)

    def _frame_field(self, layout, column, title, name):
        label = QtWidgets.QLabel(title)
        field = QtWidgets.QDoubleSpinBox()
        field.setObjectName(name)
        field.setAccessibleName(title)
        field.setDecimals(3)
        field.setRange(-1e8, 1e8)
        field.valueChanged.connect(self._sync_controls)
        label.setBuddy(field)
        layout.addWidget(label, 0, column)
        layout.addWidget(field, 1, column)
        return field

    @staticmethod
    def _disclosure(layout, title, body):
        disclosure = Disclosure(title)
        disclosure.toggle.setFocusPolicy(QtCore.Qt.StrongFocus)
        disclosure.content.addWidget(body)
        layout.addWidget(disclosure)
        return disclosure.toggle

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self._frame_timer.start()

    def hideEvent(self, event):
        self._frame_timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _resolve(node_id):
        nodes = (cmds.ls(node_id, long=True) or []) if node_id else []
        return nodes[0] if len(nodes) == 1 else None

    @staticmethod
    def _id(node):
        identities = cmds.ls(node, uuid=True) or []
        if len(identities) != 1:
            raise ValueError("The selected transform is no longer available.")
        return identities[0]

    @staticmethod
    def _show_pick(field, node, world=False, missing=False):
        text = _short(node) if node or world else ""
        if field.text() != text:
            field.setText(text)
        field.setPlaceholderText("No longer in scene" if missing else field.accessibleName())
        field.setToolTip(node or ("World" if world else ""))

    def _pick_object(self):
        try:
            self._object_id = self._id(_selected_transform())
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status()
        self.refresh()

    def _pick_parent(self):
        try:
            self._parent_id = self._id(_selected_transform())
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._world = False
        self._set_status()
        self.refresh()

    def _pick_world(self):
        self._parent_id = None
        self._world = True
        self._set_status()
        self.refresh()

    def refresh(self):
        """Refresh scene picks, points, history, and active relationship."""
        self._read_context(float(cmds.currentTime(query=True)), force=True)
        self._refresh_history()
        if self.isVisible():
            refresh_parent_manager_timeline()

    def _poll_frame(self):
        frame = float(cmds.currentTime(query=True))
        if frame != self._frame:
            self._read_context(frame)

    def _read_context(self, frame, force=False):
        self._frame = frame
        old_object, old_parent = self._object, self._parent
        self._object = self._resolve(self._object_id)
        self._parent = self._resolve(self._parent_id)
        self._show_pick(self.object_field, self._object, missing=bool(self._object_id and not self._object))
        self._show_pick(self.parent_field, self._parent, world=self._world, missing=bool(self._parent_id and not self._parent))
        if force or old_parent != self._parent:
            if old_parent != self._parent:
                with QtCore.QSignalBlocker(self.point_combo):
                    self.point_combo.setCurrentIndex(0)
            self._refresh_points()
        if force or old_object != self._object:
            self._refresh_follow_keys()
        if not force and old_object != self._object:
            self._refresh_history()
        self._active = None
        self._active_known = bool(self._object)
        if self._object:
            try:
                self._active = engine.state(self._object)
            except (ValueError, RuntimeError) as exc:
                self._active_known = False
                self._set_status(str(exc), error=True)
        self._sync_controls()

    def _refresh_points(self, prefer=None):
        previous = prefer or self.point_combo.currentData()
        self._points = []
        if self._parent:
            try:
                self._points = engine.list_points(self._parent)
            except (ValueError, RuntimeError) as exc:
                self._set_status(str(exc), error=True)
        with QtCore.QSignalBlocker(self.point_combo):
            self.point_combo.clear()
            self.point_combo.addItem("Don’t snap to an attach point", None)
            for point in self._points:
                self.point_combo.addItem(_color_icon(point["color"]), point["name"], point["node"])
            if self._parent or self._world:
                self.point_combo.addItem("World origin" if self._world else "Object origin", _ORIGIN)
            index = self.point_combo.findData(previous) if previous else 0
            self.point_combo.setCurrentIndex(max(0, index))
        if not self.point_combo.currentData():
            self.timing_toggle.setChecked(False)
        with QtCore.QSignalBlocker(self.point_labels):
            self.point_labels.setEnabled(bool(self._points))
            self.point_labels.setChecked(any(point["label_visible"] for point in self._points))

    def _toggle_point_names(self, visible):
        try:
            engine.set_point_labels(self._parent, visible)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
        else:
            self._set_status()
        self._refresh_points()

    def _point_changed(self, *_):
        if not self.point_combo.currentData():
            self.timing_toggle.setChecked(False)
        self._sync_controls()

    def _timing_toggled(self, checked):
        if checked:
            frame = cmds.currentTime(query=True)
            for field in (self.match_start, self.match_end):
                with QtCore.QSignalBlocker(field):
                    field.setValue(frame)
        self._sync_controls()

    def _point_frames(self):
        if self.timing_toggle.isChecked():
            return self.match_start.value(), self.match_end.value()
        return self._frame, self._frame

    def _preview_point(self, *_):
        self._point_changed()
        node = self.point_combo.currentData()
        if node and node != _ORIGIN and cmds.objExists(node):
            cmds.select(node, replace=True)

    def _channels(self):
        return tuple(name for name, check in self.channel_checks.items() if check.isChecked())

    def _sync_controls(self):
        if self._frame is None:
            return
        frame = _frame_text(self._frame)
        object_name = _short(self._object)
        active_target = self._active.get("target") if self._active else None
        active_name = _short(active_target)
        if self._active:
            point = self._active.get("point")
            spot = " at " + (self._active.get("name") or _short(point)) if point else ""
            summary = f"On frame {frame}, {object_name} is following {active_name}{spot}."
        elif self._active_known:
            summary = f"On frame {frame}, {object_name} is free to move."
        elif self._object:
            summary = f"On frame {frame}, Aminate couldn't check what {object_name} follows."
        else:
            summary = "Select what should move in Maya, then click Use Selection on the first line."
        self.active_label.setText(summary)
        self.active_label.setToolTip(active_target or ("World" if self._active else ""))
        point = self.point_combo.currentData()
        self.point_combo.setEnabled(bool(self._parent or self._world))
        self.match_options.setVisible(bool(point))
        self.timing_fields.setVisible(self.timing_toggle.isChecked())
        self.create_point_button.setEnabled(bool(self._parent))
        self.edit_point_button.setVisible(bool(point and point != _ORIGIN))
        switching = bool(self._active and (self._parent or self._world) and active_target != self._parent)
        self.apply_button.setText(
            "Follow this instead" if switching else "Update how it follows" if self._active else "Start following here"
        )
        can_attach = bool(
            self._active_known and (self._parent or self._world) and self._object != self._parent
            and self._channels()
        )
        self.apply_button.setEnabled(can_attach)
        if point:
            start, end = self._point_frames()
            destination = self.point_combo.currentText()
            self.match_button.setText("Snap to attach point and follow" if start == end else "Move to attach point and follow")
            if start > end:
                instructions = "Set the arrival frame on or after the start frame."
            elif start == end:
                instructions = f"Snap to {destination} on frame {_frame_text(end)}, then follow {_short(self._parent)}."
            else:
                instructions = (
                    f"Move to {destination} from frame {_frame_text(start)} to {_frame_text(end)}, "
                    f"then follow {_short(self._parent)}."
                )
            self.match_help.setText(instructions)
            self.match_button.setEnabled(can_attach and start <= end)
        self.detach_button.setEnabled(bool(self._active))
        self.detach_button.setToolTip(f"Keys the release on frame {frame}. It can move on its own again.")
        if not self._object:
            preview = ""
        elif not (self._parent or self._world):
            preview = "Select what it should follow, then click Use Selection on the second line."
        elif self._object == self._parent:
            preview = "Choose something else to follow. An object can't follow itself."
        elif not self._channels():
            preview = "Turn on Move, Turn or Resize under to follow."
        else:
            target_name = _short(self._parent)
            if switching:
                preview = f"Keys the change on this frame. It stops following {active_name} and follows {target_name} without jumping."
            else:
                preview = f"Keys the follow on this frame. It keeps its pose and follows {target_name}."
        self.next_action.setText(preview)
        self.next_action.setVisible(bool(preview))
        self.apply_button.setToolTip(preview or "Pick what should move first.")

    def _set_status(self, text="", error=False):
        role = "error" if error else "success"
        if self.status.property("aminateRole") != role:
            self.status.setProperty("aminateRole", role)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def _refresh_follow_keys(self):
        self._follow_key_plugs = engine.follow_key_plugs(self._object)
        frames = sorted({
            frame for plug in self._follow_key_plugs
            for frame in (cmds.keyframe(plug, query=True, timeChange=True) or [])
        })
        if frames:
            shown = ", ".join(_frame_text(frame) for frame in frames[:6])
            if len(frames) > 6:
                shown += f" and {len(frames) - 6} more"
            summary = f"Follow keys at frames {shown}. Hover over a coloured tick for details."
        else:
            summary = "Follow keys will appear here after you start following."
        self.key_summary.setText(summary if self._object else "")
        self.key_summary.setVisible(bool(self._object))
        self.key_button.setVisible(bool(frames))
        self.key_summary.setToolTip(
            "Show follow keys selects the native Maya keys. The coloured follow ticks stay visible on the Time Slider."
        )

    def _select_follow_keys(self):
        self.refresh()
        if self.key_button.isHidden():
            return
        try:
            plugs = engine.prepare_follow_display(self._object)
            if not plugs:
                return
            cmds.select(plugs[0].split(".", 1)[0], replace=True)
            cmds.selectKey(clear=True)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self.refresh()
        slider = mel.eval("$tmp = $gPlayBackSlider")
        if cmds.timeControl(slider, query=True, showKeys=True) != "active":
            self._set_status("Ticks hidden? Right-click the Time Slider and choose Display Key Ticks > Active.")
        else:
            self._set_status("Follow colours are shown in the Time Slider. Move or remove changes in Follow history.")

    def _attach(self):
        self._apply_follow(at_point=False)

    def _attach_at_point(self):
        self._apply_follow(at_point=True)

    def _apply_follow(self, at_point):
        point = self.point_combo.currentData() if at_point else None
        self.refresh()
        if at_point and point != self.point_combo.currentData():
            self._set_status("That attach point is gone. Choose another point.", error=True)
            return
        button = self.match_button if at_point else self.apply_button
        if not button.isEnabled() or (at_point and not point):
            return
        start, end = self._point_frames() if at_point else (None, None)
        try:
            engine.attach(
                self._object, self._parent, point=None if point == _ORIGIN else point,
                channels=self._channels(),
                match_start=start, end_frame=end,
            )
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        if at_point:
            self.timing_toggle.setChecked(False)
        self._set_status()
        self.refresh()

    def _detach(self):
        self.refresh()
        if not self._active:
            return
        try:
            engine.detach(self._object)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status()
        self.refresh()

    def _create_point(self):
        if not self._parent:
            return
        try:
            source_id = self._id(_selected_transform())
        except (ValueError, RuntimeError):
            self._set_status("Select one locator or control where you want the object to go.", error=True)
            return
        source = self._resolve(source_id)
        description = f"Save the position and angle of {_short(source)} on {_short(self._parent)}."
        values = self._point_dialog("Save a new attach point", "New attach point", _POINT_COLORS[0][1], description)
        if values is None:
            return
        try:
            parent = self._resolve(self._parent_id)
            source = self._resolve(source_id)
            if not (parent and source):
                raise ValueError("The target or the selected object is no longer in the scene.")
            point = engine.create_point(parent, source, *values)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._refresh_points(prefer=point)
        self._preview_point()
        self._set_status("Saved attach point " + values[0] + ".")

    def _edit_point(self):
        node = self.point_combo.currentData()
        point = next((point for point in self._points if point["node"] == node), None)
        if point is None:
            return
        values = self._point_dialog("Edit attach point", point["name"], point["color"])
        if values is None:
            return
        try:
            engine.update_point(node, *values)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status("Updated attach point " + values[0] + ".")
        self.refresh()

    def _point_dialog(self, title, point_name, rgb, description=""):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        form = QtWidgets.QFormLayout(dialog)
        if description:
            form.addRow(self._label(description))
        name = QtWidgets.QLineEdit(point_name)
        name.setAccessibleName("Attach point name")
        color = QtWidgets.QComboBox()
        color.setAccessibleName("Viewport color")
        selected = None
        for index, (label, value) in enumerate(_POINT_COLORS):
            color.addItem(_color_icon(value), label, value)
            if all(abs(a - b) < 1e-5 for a, b in zip(value, rgb)):
                selected = index
        if selected is None:
            color.addItem(_color_icon(rgb), "Current color", tuple(rgb))
            selected = color.count() - 1
        color.setCurrentIndex(selected)
        form.addRow("Name", name)
        form.addRow("Viewport color", color)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        name.textChanged.connect(lambda text: buttons.button(QtWidgets.QDialogButtonBox.Save).setEnabled(bool(text.strip())))
        form.addRow(buttons)
        name.setFocus()
        name.selectAll()
        if not dialog.exec_():
            return None
        return name.text().strip(), tuple(color.currentData())

    def _refresh_history(self):
        if not self.history_toggle.isChecked():
            return
        selected = self.history_list.currentItem()
        selected_frame = selected.data(0, QtCore.Qt.UserRole) if selected else None
        self.history_list.clear()
        events = ()
        missing = False
        text = "Pick what should move to see its follow changes."
        if self._object:
            try:
                events = engine.history(self._object)
                missing = bool(events and engine.missing_bookmarks(self._object))
            except (ValueError, RuntimeError) as exc:
                text = str(exc)
            else:
                text = (
                    "Pick a row to jump to that frame. Move or remove it here to keep the animation and timeline together."
                    if events else "No follow changes yet."
                )
        self.history_hint.setText(text)
        self.history_list.setVisible(bool(events))
        self.history_actions.setVisible(bool(events))
        self.bookmarks_button.setVisible(missing)
        light_background = self.history_list.palette().color(QtGui.QPalette.Base).lightness() >= 128
        for entry in events:
            frame = _frame_text(entry["frame"])
            if entry["start"] < entry["frame"]:
                frame = _frame_text(entry["start"]) + "–" + frame
            if entry["action"] == "detach":
                item = QtWidgets.QTreeWidgetItem((frame, "Free"))
                details = "Stops following and keeps its pose."
            else:
                target, target_id = entry["target"], entry["target_id"]
                name = _short(target) if target or not target_id else "Missing parent"
                if entry["point"]:
                    name += " · " + (entry["name"] or _short(entry["point"]))
                item = QtWidgets.QTreeWidgetItem((frame, name))
                channels = ", ".join(channel.title() for channel in entry["channels"])
                details = f"{name}\n{channels}"
                if target:
                    details += "\n" + target
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(engine.follow_color(entry["color_index"], light_background))))
            item.setData(0, QtCore.Qt.UserRole, entry["frame"])
            item.setData(1, QtCore.Qt.UserRole, entry["protected_release"])
            item.setToolTip(0, "Jump to frame " + _frame_text(entry["frame"]))
            item.setToolTip(1, details)
            self.history_list.addTopLevelItem(item)
            if entry["frame"] == selected_frame:
                self.history_list.setCurrentItem(item)

    def _sync_history_actions(self, *_):
        item = self.history_list.currentItem()
        for widget in (self.earlier_button, self.later_button, self.destination_frame,
                       self.move_button, self.remove_button):
            widget.setEnabled(item is not None)
        self.release_hint.setVisible(bool(item and item.data(1, QtCore.Qt.UserRole)))
        if item:
            self.destination_frame.setValue(item.data(0, QtCore.Qt.UserRole))

    def _nudge_follow_change(self, offset):
        item = self.history_list.currentItem()
        if item:
            self._move_follow_change(item.data(0, QtCore.Qt.UserRole) + offset)

    def _move_follow_change(self, destination):
        item = self.history_list.currentItem()
        if item is None:
            return
        frame = item.data(0, QtCore.Qt.UserRole)
        if destination == frame:
            self._set_status("Enter the new frame, then click Move to frame.")
            return
        try:
            engine.move_follow_change(self._resolve(self._object_id), frame, destination, jump=True)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self.refresh()
        for index in range(self.history_list.topLevelItemCount()):
            row = self.history_list.topLevelItem(index)
            if row.data(0, QtCore.Qt.UserRole) == destination:
                self.history_list.setCurrentItem(row)
                break
        self._set_status(f"Moved the follow change to frame {_frame_text(destination)}.")

    def _remove_follow_change(self):
        item = self.history_list.currentItem()
        if item is None:
            return
        frame = item.data(0, QtCore.Qt.UserRole)
        try:
            engine.remove_follow_change(self._resolve(self._object_id), frame)
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self.refresh()
        self._set_status(f"Removed the follow change on frame {_frame_text(frame)}. Maya Undo brings it back.")

    def _add_bookmarks(self):
        try:
            engine.add_bookmarks(self._resolve(self._object_id))
        except (ValueError, RuntimeError) as exc:
            self._set_status(str(exc), error=True)
            return
        self.refresh()
        self._set_status("Hover over a bookmark above the Time Slider to see what changes.")

    def _jump_to_frame(self, item, _column):
        cmds.currentTime(float(item.data(0, QtCore.Qt.UserRole)))
        self._poll_frame()
