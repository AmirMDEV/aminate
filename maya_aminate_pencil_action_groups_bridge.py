"""Idempotent retained-session regrouping for Animator's Pencil actions.

Older Aminate panels can remain cached in a live Maya process after the source
module is updated.  This bridge moves the already-created widgets into the
same Layer Controls, Selected Mark Editing, and Pencil History groups without
reloading modules, rebuilding the window, or reconnecting any signals.
"""

from __future__ import absolute_import, print_function

try:
    from PySide6 import QtWidgets
except Exception:
    try:
        from PySide2 import QtWidgets
    except Exception:
        QtWidgets = None


def _valid(widget):
    if widget is None:
        return False
    try:
        widget.objectName()
        return True
    except Exception:
        return False


def _find_direct_layout_index(layout, widget):
    """Return the outer index containing *widget* directly or recursively."""
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            return index
        child_layout = item.layout()
        if child_layout is not None and _find_direct_layout_index(child_layout, widget) is not None:
            return index
    return None


def _remove_from_layout(layout, widget):
    """Remove *widget* from nested layouts without changing its parent."""
    if layout is None:
        return
    for index in range(layout.count() - 1, -1, -1):
        item = layout.itemAt(index)
        child_layout = item.layout()
        if child_layout is not None:
            _remove_from_layout(child_layout, widget)
        elif item.widget() is widget:
            layout.removeWidget(widget)


def _prune_empty_layouts(layout):
    """Remove now-empty nested layouts so retained panels do not keep gaps."""
    if layout is None:
        return
    for index in range(layout.count() - 1, -1, -1):
        item = layout.itemAt(index)
        child_layout = item.layout()
        if child_layout is None:
            continue
        _prune_empty_layouts(child_layout)
        if child_layout.count() == 0:
            layout.takeAt(index)


def _add_help(layout, object_name, text, tooltip):
    label = QtWidgets.QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setToolTip(tooltip)
    layout.addWidget(label)
    return label


def _group(parent, title, object_name, accessible, tooltip):
    group = QtWidgets.QGroupBox(title, parent)
    group.setObjectName(object_name)
    group.setAccessibleName(accessible)
    group.setToolTip(tooltip)
    group.setMinimumWidth(0)
    policy = group.sizePolicy()
    policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Ignored)
    group.setSizePolicy(policy)
    return group


def _replace_widget_in_layout(layout, old_widget, new_widget):
    if layout is None:
        return False
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is old_widget:
            if isinstance(layout, QtWidgets.QGridLayout):
                row, column, row_span, column_span = layout.getItemPosition(index)
                layout.removeWidget(old_widget)
                layout.addWidget(new_widget, row, column, row_span, column_span)
            elif isinstance(layout, QtWidgets.QBoxLayout):
                stretch = layout.stretch(index)
                alignment = item.alignment()
                layout.removeWidget(old_widget)
                layout.insertWidget(index, new_widget, stretch, alignment)
            else:
                layout.removeWidget(old_widget)
                layout.addWidget(new_widget)
            return True
        child_layout = item.layout()
        if child_layout is not None and _replace_widget_in_layout(child_layout, old_widget, new_widget):
            return True
        child_widget = item.widget()
        if child_widget is not None and child_widget.layout() is not None:
            if _replace_widget_in_layout(child_widget.layout(), old_widget, new_widget):
                return True
    return False


def _ensure_rename_push_button(panel):
    old_button = getattr(panel, "rename_layer_button", None)
    if isinstance(old_button, QtWidgets.QPushButton):
        return old_button
    if not _valid(old_button):
        return old_button
    new_button = QtWidgets.QPushButton("Rename Layer", old_button.parentWidget())
    new_button.setObjectName("animatorsPencilRenameLayerButton")
    new_button.setAccessibleName("Rename selected Pencil layer")
    new_button.setToolTip("Rename the selected Pencil layer using the name above. Double-clicking its table name works too.")
    new_button.clicked.connect(old_button.click)
    if not _replace_widget_in_layout(panel.layout(), old_button, new_button):
        new_button.setObjectName("animatorsPencilRenameLayerButtonUnused")
        new_button.hide()
        return old_button
    old_button.setObjectName("animatorsPencilRenameLayerButtonLegacy")
    old_button.hide()
    panel.rename_layer_button = new_button
    return new_button


def _apply_action_clarity(panel):
    """Apply action labels and explanations even when groups already exist."""
    specifications = (
        ("layer_name", None, "Name for the selected Pencil layer. Double-click a layer name in the table to rename it too.", "Selected Pencil layer name"),
        ("add_layer_button", "Add Layer", "Create a new Pencil layer using the name above.", "Add a new Pencil layer"),
        ("rename_layer_button", "Rename Layer", "Rename the selected Pencil layer using the name above. Double-clicking its table name works too.", "Rename selected Pencil layer"),
        ("delete_layer_button", "Delete Layer", "Delete the selected Pencil layer and its marks.", "Delete selected Pencil layer"),
        ("hide_all_layers_button", "Hide All", "Hide every Animator's Pencil layer for a clean playblast.", "Hide all Pencil layers"),
        ("show_all_layers_button", "Show All", "Show every Animator's Pencil layer again.", "Show all Pencil layers"),
        ("state_combo", None, "Choose whether the selected Pencil layer is animated, static, or locked.", "Selected Pencil layer state"),
        ("layer_opacity_spin", None, "Persistent opacity for every existing and future mark in the selected layer.", "Selected Pencil layer opacity percentage"),
        ("layer_up_button", "Layer Up", "Move the selected Pencil layer one step higher in the layer stack.", "Move selected Pencil layer up"),
        ("layer_down_button", "Layer Down", "Move the selected Pencil layer one step lower in the layer stack.", "Move selected Pencil layer down"),
        ("move_camera_button", "Move To Current Camera", "Attach the selected Pencil layer to the camera currently shown in the active viewport.", "Move selected Pencil layer to current camera"),
        ("copy_button", "Copy Selected Marks", "Copy the selected Pencil marks to the clipboard without changing the current layer.", "Copy selected Pencil marks"),
        ("cut_button", "Cut Selected Marks", "Copy and remove the selected Pencil marks from their current layer.", "Cut selected Pencil marks"),
        ("paste_button", "Paste Marks", "Paste copied Pencil marks into the active layer at the current frame.", "Paste Pencil marks"),
        ("delete_marks_button", "Erase Selected Marks", "Erase the selected Pencil marks. The layer itself is left unchanged.", "Erase selected Pencil marks"),
        ("translucent_button", "Toggle Mark Translucency", "Toggle Maya's translucent/template display for the selected Pencil marks.", "Toggle selected Pencil mark translucency"),
        ("undo_button", "Undo Pencil Edit", "Undo the most recent Animator's Pencil edit.", "Undo last Animator Pencil edit"),
        ("redo_button", "Redo Pencil Edit", "Redo the most recently undone Animator's Pencil edit.", "Redo last Animator Pencil edit"),
    )
    for name, label, tooltip, accessible_name in specifications:
        widget = getattr(panel, name, None)
        if not _valid(widget):
            continue
        if label is not None and hasattr(widget, "setText"):
            widget.setText(label)
        widget.setToolTip(tooltip)
        widget.setAccessibleName(accessible_name)


def install_into_open_aminate(panel=None):
    """Regroup the existing Animator's Pencil panel and return it.

    The operation is deliberately idempotent.  A second call returns the
    existing panel untouched, so callbacks and the current Maya window stay
    exactly as they were.
    """
    if QtWidgets is None:
        raise RuntimeError("Qt bindings are unavailable")
    if panel is None:
        try:
            import maya_dynamic_parent_pivot as workflow

            window = getattr(workflow, "GLOBAL_WINDOW", None)
            panel = getattr(window, "animators_pencil_panel", None)
            if panel is None:
                import maya_animators_pencil as pencil

                pencil_window = getattr(pencil, "GLOBAL_WINDOW", None)
                panel = getattr(pencil_window, "panel", None)
        except Exception:
            panel = None
    if not _valid(panel):
        raise RuntimeError("Open Aminate Animator's Pencil panel was not found")
    _ensure_rename_push_button(panel)
    existing = panel.findChild(QtWidgets.QGroupBox, "animatorsPencilLayerControlsGroup")
    if existing is not None:
        _apply_action_clarity(panel)
        return panel

    names = (
        "layer_name", "add_layer_button", "rename_layer_button", "delete_layer_button",
        "hide_all_layers_button", "show_all_layers_button", "layer_table", "state_combo",
        "layer_opacity_spin", "layer_up_button", "layer_down_button", "move_camera_button",
        "copy_button", "cut_button", "paste_button", "delete_marks_button",
        "translucent_button", "undo_button", "redo_button",
    )
    widgets = {name: getattr(panel, name, None) for name in names}
    if any(not _valid(widget) for widget in widgets.values()):
        raise RuntimeError("Cached Pencil panel is missing an expected action widget")

    outer = panel.layout()
    insertion_index = None
    for widget in widgets.values():
        found = _find_direct_layout_index(outer, widget)
        if found is not None:
            insertion_index = found if insertion_index is None else min(insertion_index, found)
    for widget in widgets.values():
        _remove_from_layout(outer, widget)
    _prune_empty_layouts(outer)
    if insertion_index is None:
        insertion_index = outer.count()

    layer_tip = "Controls in this section change the selected Pencil layer: its name, visibility, order, camera, state, and opacity."
    layer = _group(panel, "Layer Controls", "animatorsPencilLayerControlsGroup", "Animator Pencil layer controls", layer_tip)
    layer_layout = QtWidgets.QVBoxLayout(layer)
    _add_help(layer_layout, "animatorsPencilLayerControlsHelp", "Selected layer: rename, show or hide, change its state and opacity, or move it in the layer stack.", layer_tip)
    for name in ("layer_name", "add_layer_button", "rename_layer_button", "delete_layer_button", "hide_all_layers_button", "show_all_layers_button", "layer_table", "state_combo", "layer_opacity_spin", "layer_up_button", "layer_down_button", "move_camera_button"):
        layer_layout.addWidget(widgets[name])

    mark_tip = "These actions affect the selected Pencil marks. They do not move, rename, or change the active layer."
    marks = _group(panel, "Selected Mark Editing", "animatorsPencilSelectedMarkEditingGroup", "Animator Pencil selected mark editing", mark_tip)
    marks_layout = QtWidgets.QVBoxLayout(marks)
    _add_help(marks_layout, "animatorsPencilSelectedMarkEditingHelp", "Select marks in the viewport, then copy, cut, paste, erase, or change their display state.", mark_tip)
    for name in ("copy_button", "cut_button", "paste_button", "delete_marks_button", "translucent_button"):
        marks_layout.addWidget(widgets[name])

    history_tip = "Undo or redo recent Animator's Pencil edits."
    history = _group(panel, "Pencil History", "animatorsPencilHistoryGroup", "Animator Pencil edit history", history_tip)
    history_layout = QtWidgets.QVBoxLayout(history)
    _add_help(history_layout, "animatorsPencilHistoryHelp", "Step backward or forward through recent Pencil edits.", history_tip)
    history_layout.addWidget(widgets["undo_button"])
    history_layout.addWidget(widgets["redo_button"])

    _apply_action_clarity(panel)

    outer.insertWidget(insertion_index, layer)
    outer.insertWidget(insertion_index + 1, marks)
    outer.insertWidget(insertion_index + 2, history)
    panel.layer_controls_group = layer
    panel.selected_mark_editing_group = marks
    panel.history_group = history
    panel._aminate_action_groups_bridge_installed = True
    return panel


__all__ = ["install_into_open_aminate"]
