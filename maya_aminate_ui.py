"""Shared compact task layouts. Moves existing widgets; never replaces callbacks."""
from __future__ import absolute_import, division, print_function

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


class Disclosure(QtWidgets.QWidget):
    def __init__(self, title, expanded=False, parent=None):
        super(Disclosure, self).__init__(parent)
        self.setObjectName('aminateSection_' + ''.join(c if c.isalnum() else '_' for c in title))
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setObjectName("aminateIntroToggle")
        self.toggle.setText(title)
        self.toggle.setAccessibleName(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.body = QtWidgets.QWidget()
        self.content = QtWidgets.QVBoxLayout(self.body)
        self.content.setContentsMargins(6, 2, 0, 6)
        self.content.setSpacing(6)
        outer.addWidget(self.toggle)
        outer.addWidget(self.body)
        self.toggle.toggled.connect(self.setExpanded)
        self.setExpanded(expanded)

    def setExpanded(self, expanded):
        self.toggle.setChecked(bool(expanded))
        self.toggle.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.body.setVisible(bool(expanded))


def detach(owner, item):
    # Search actual layout ownership, including rows inside scroll-area content.
    for layout in owner.findChildren(QtWidgets.QLayout):
        for index in range(layout.count() - 1, -1, -1):
            child = layout.itemAt(index)
            if child.widget() is item or child.layout() is item:
                layout.takeAt(index)
                if isinstance(item, QtWidgets.QLayout):
                    item.setParent(None)
                return


def add(layout, item):
    if isinstance(item, QtWidgets.QLayout):
        layout.addLayout(item)
    else:
        layout.addWidget(item)


def section(owner, title, items, expanded=False):
    panel = Disclosure(title, expanded)
    for item in items:
        detach(owner, item)
        add(panel.content, item)
    return panel


def arrange(owner, root, groups):
    panels = [section(owner, title, items, expanded) for title, expanded, items in groups]
    remaining = []
    while root.count():
        remaining.append(root.takeAt(0))
    for item in list(remaining):
        if item.widget() and item.widget().objectName() == "aminateTabIntro":
            root.addItem(item)
            remaining.remove(item)
    for panel in panels:
        root.addWidget(panel)
    for item in remaining:
        root.addItem(item)
    status = getattr(owner, 'status_label', None)
    if status is not None and root.indexOf(status) >= 0:
        root.removeWidget(status)
        root.insertWidget(min(1, root.count()), status)
    return panels


def primary(button, text=None):
    if text:
        button.setText(text)
    button.setProperty('aminateRole', 'primary')


def action_grid(owner, items):
    grid = QtWidgets.QGridLayout()
    for index, item in enumerate(items):
        detach(owner, item)
        grid.addWidget(item, index // 2, index % 2)
    return grid


def resolve(owner, local, name):
    if name.startswith('self.'):
        return getattr(owner, name[5:])
    return local[name]


# root layout, (heading, expanded, existing layout/widget names)
RECIPES = {
 'contact': ('main_layout', [
  ('1. Control and contact range', True, 'controls_row frame_grid'),
  ('2. Create or update hold', True, 'axis_box self.keep_rotation_check create_row'),
  ('Saved holds', True, 'hold_group'),
  ('Names and details', False, 'alias_row self.report_box intro')]),
 'surface': ('main_layout', [
  ('1. Controls and surfaces', True, 'controls_row surfaces_row'),
  ('2. Create contact', True, 'action_layout'),
  ('Collision options', False, 'options_group'),
  ('Saved contacts', True, 'collision_group'),
  ('Details', False, 'intro self.report_box')]),
 'parenting': ('main_layout', [
  ('1. Object', True, 'object_group'), ('2. Parent and switch', True, 'target_group self.parent_to_world_button'),
  ('Previous switches', False, 'history_group'),
  ('More options', False, 'self.advanced_toggle self.advanced_widget'),
  ('Help', False, 'intro')]),
 'retarget': ('main_layout', [
  ('1. Source and target pairs', True, 'pair_map_group action_row'),
  ('2. Retarget', True, 'retarget_row'),
  ('Motion options', False, 'options_row'),
  ('Saved pairs and manual mapping', False, 'advanced_group'),
  ('Details', False, 'intro_group self.report_box')]),
 'rotation': ('main_layout', [
  ('1. Analyse selected controls', True, 'self.analyze_button'),
  ('2. Review findings', True, 'self.split_layout'),
  ('3. Apply fix', True, 'self.apply_recommended_button self.flip_current_key_button'),
  ('Advanced cleanup', False, 'self.euler_cleanup_button self.preserve_spins_button self.sync_euler_button self.quaternion_button self.custom_pass_button self.clear_button'),
  ('Help', False, 'description note')]),
 'rig_scale': ('main_layout', [
  ('1. Rig and target size', True, 'roots_group'),
  ('2. Create export copy', True, 'action_row'),
  ('3. Export copy', True, 'self.select_button self.export_button'),
  ('Copy management', False, 'self.advanced_toggle self.advanced_body'),
  ('Details', False, 'description note self.report_text')]),
 'assistant': ('layout', [
  ('1. Character and ground', True, 'setup_group'),
  ('2. Contact points', True, 'contacts_group'),
  ('Preview limitations and help', False, 'self.help_box')]),
 'styling': ('layout', [
  ('1. Hold settings', True, 'header'),
  ('2. Style existing keys', True, 'self.apply_selected_button self.apply_current_button'),
  ('Overlap warnings', True, 'self.scan_button self.clear_button'),
  ('Help', False, 'self.help_box')]),
 'picker': ('main_layout', [
  ('Rig', True, 'self.controls_root_edit self.use_selected_controls_root_button self.scan_selected_button'),
  ('Select controls', True, 'self.view_tabs self.select_in_maya_button self.toggle_fkik_button'),
  ('Edit layout', False, 'root_grid root_row action_row label_row custom_row'),
  ('Help', False, 'intro')]),
 'pencil': ('layout', [
  ('Draw', True, 'self.active_tool_strip'),
  ('Layers', True, 'layer_group layers_heading self.layer_table'),
  ('Drawing options', False, 'self.drawing_settings'),
  ('Views and video', False, 'drawing_views self.video_draw_over_group'),
  ('Edit marks', False, 'mark_group history_group transform'),
  ('Animation', False, 'onion anim'),
  ('Help', False, 'intro')]),
 'history': ('layout', [
  ('Save and restore', True, 'form self.save_step_button self.save_milestone_button self.restore_button'),
  ('Manage snapshots', False, 'self.rename_button self.color_button self.toggle_milestone_button self.delete_button self.delete_all_button self.open_folder_button'),
  ('Snapshots', True, 'table_box self.strip'),
  ('Branches', False, 'self.branch_graph branch_row'),
  ('Storage and automatic saves', False, 'settings_box auto_box'),
  ('Help', False, 'intro')]),
 'video': ('main_layout', [
  ('1. Choose media', True, 'source_group'),
  ('2. Place reference', True, 'placement_group'),
  ('3. Create or update', True, 'self.import_button'),
  ('Draw over reference', False, 'self.open_layers_button self.draw_button'),
  ('Help', False, 'help_toggle help_box intro')]),
 'skin_cleanup': ('main_layout', [
  ('Fix mesh transforms', True, 'self.create_button self.character_copy_button'),
  ('Inspect or replace original', False, 'self.advanced_toggle self.advanced_body'),
  ('Details', False, 'description note self.report_text')]),
 'skin_transfer': ('main_layout', [
  ('Source and target meshes', True, 'grid'),
  ('Quick copy from selection', False, 'self.copy_selected_button'),
  ('Options', False, 'policy_row'),
  ('Help', False, 'title help_text note')]),
 'fbx': ('root', [
  ('Export selected animation', True, 'output_row self.range_label'),
  ('Options', False, 'settings axis_row'),
  ('Export', True, 'self.overwrite_checkbox buttons'),
  ('Help', False, 'intro')]),
 'pivot': ('layout', [
  ('1. Place pivot', True, 'pivot_group self.create_pivot_button self.edit_pivot_button'),
  ('2. Rotate around pivot', True, 'self.apply_pivot_button self.clear_pivot_button self.pivot_range_status'),
  ('Help', False, 'summary self.pivot_help')]),
 'ikfk': ('layout', [
  ('Use saved switch', True, 'saved_group self.switch_fk_to_ik_button self.switch_ik_to_fk_button'),
  ('Set up rig', False, 'setup_group fk_group ik_group self.detect_profile_button self.save_profile_button'),
  ('Advanced matching', False, 'details_group'),
  ('Help', False, 'summary self.ikfk_help')]),
}


def apply(owner, key, local):
    """Called after a panel has built and connected its original controls."""
    if key in RECIPES:
        root_name, recipe = RECIPES[key]
        groups = [(title, expanded, [resolve(owner, local, name) for name in names.split()]) for title, expanded, names in recipe]
        owner._task_sections = arrange(owner, local[root_name], groups)
    if key == 'contact':
        primary(owner.apply_button, 'Create Hold')
        owner.update_button.setText('Update Hold')
        def sync_hold_action():
            selected = bool(owner.holds_table.selectionModel().selectedRows())
            owner.apply_button.setVisible(not selected)
            owner.update_button.setVisible(selected)
        owner.holds_table.itemSelectionChanged.connect(sync_hold_action)
        sync_hold_action()
        new_button = QtWidgets.QPushButton('New hold')
        new_button.clicked.connect(owner.holds_table.clearSelection)
        owner._task_sections[2].content.addWidget(new_button)
    elif key == 'surface':
        primary(owner.apply_button, 'Create / Update Contact')
    elif key == 'parenting':
        primary(owner.parent_to_row_button, 'Switch to Selected Parent')
        owner.maintain_offset_check.setText('Keep current position (off = snap to parent)')
        owner.save_offset_button.hide()
        owner.save_offset_row_button.hide()
        offset = QtWidgets.QPushButton('Save Current Offset')
        offset.setToolTip('Save the current pose for the selected parent row, or the picked parent when no row is selected.')
        offset.clicked.connect(lambda: owner.save_offset_row_button.click() if owner._selected_target_ids() else owner.save_offset_button.click())
        owner._task_sections[3].content.insertWidget(0, offset)
        owner.save_current_offset_button = offset
        # Existing advanced disclosure is redundant inside More options.
        owner.advanced_toggle.setChecked(True)
        owner.advanced_toggle.hide()
        owner.advanced_widget.show()
    elif key == 'retarget':
        primary(owner.retarget_all_button, 'Retarget')
        owner.retarget_selected_button.hide()
        scope = QtWidgets.QComboBox()
        scope.addItems(['All pairs', 'Selected saved pairs'])
        scope.setAccessibleName('Retarget scope')
        local['retarget_row'].insertWidget(0, scope)
        owner.retarget_scope = scope
        owner.retarget_all_button.clicked.disconnect()
        owner.retarget_all_button.clicked.connect(lambda _checked=False: owner._retarget_selected_pairs() if scope.currentIndex() else owner._retarget_all_pairs())
        scope.currentIndexChanged.connect(lambda index: owner._task_sections[3].setExpanded(bool(index)))
    elif key == 'rotation':
        primary(owner.apply_recommended_button, 'Apply Recommended Fix')
    elif key == 'rig_scale':
        primary(owner.create_button, 'Create Export Copy')
        owner.advanced_toggle.setChecked(True); owner.advanced_toggle.hide(); owner.advanced_body.show()
    elif key == 'assistant':
        owner._task_sections[0].toggle.setText('Pose Balance (Preview)')
        owner.enabled_check.setText('Show Balance Overlay')
        label = local['setup_layout'].itemAtPosition(5, 0).widget()
        calibration = section(owner, 'Calibration', [label, owner.threshold_spin, owner.refresh_button], False)
        local['layout'].insertWidget(2, calibration)
    elif key == 'styling':
        primary(owner.apply_selected_button, 'Apply to Selected Controls')
        owner.enabled_check.setText('Automatically hold future keys')
        owner.step_curves_check.setText('Use stepped curves (whole scene)')
    elif key == 'history':
        local['actions_box'].hide()
        owner.restore_button.setText('Restore Selected Snapshot')
    elif key == 'picker':
        owner.view_tabs.setCurrentWidget(owner.visual_page)
        owner._task_sections[2].toggle.setText('Edit Layout / Rig Setup')
    elif key == 'video':
        # File rows are stacked so browse buttons stay reachable in narrow docks.
        for name in ('camera_row', 'media_row', 'audio_row', 'target_row'):
            local[name].setDirection(QtWidgets.QBoxLayout.TopToBottom)
        placement = QtWidgets.QFormLayout()
        placement.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        for title, field in [('Placement', owner.placement_combo), ('Start frame', owner.start_spin)]:
            detach(owner, field); placement.addRow(title, field)
        owner._task_sections[1].content.insertLayout(0, placement)
        local['placement_group'].hide()
        settings = QtWidgets.QFormLayout()
        settings.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        for title, field in [('Card width', owner.card_width_spin), ('Back distance', owner.depth_offset_spin), ('Opacity', owner.opacity_spin)]:
            detach(owner, field); settings.addRow(title, field)
        options = section(owner, 'Reference options', [settings, local['axis_row'], owner.import_audio_check, owner.update_timing_button], False)
        local['main_layout'].insertWidget(3, options)
        local['draw_group'].hide()
        primary(owner.import_button, 'Create / Update Reference')
        owner.open_layers_button.setText('Open Pencil')
    elif key == 'skin_cleanup':
        primary(owner.create_button, 'Create Mesh with Clean Transforms')
        owner.advanced_toggle.setChecked(True); owner.advanced_toggle.hide(); owner.advanced_body.show()
    elif key == 'skin_transfer':
        primary(owner.copy_loaded_button, 'Copy Skin Weights')
    elif key == 'fbx':
        owner.setMinimumWidth(320)
        summary = QtWidgets.QLabel()
        summary.setWordWrap(True)
        owner._task_sections[0].content.addWidget(summary)
        def update_summary():
            controls = local['settings'].findChildren(QtWidgets.QCheckBox)
            selected = [c.text() for c in controls if c.isChecked()]
            summary.setText('Includes: ' + (', '.join(selected) if selected else 'selected animation only'))
        for control in local['settings'].findChildren(QtWidgets.QCheckBox):
            control.toggled.connect(update_summary)
        update_summary()
    elif key == 'pivot':
        primary(owner.create_pivot_button, 'Place Pivot')
        owner.edit_pivot_button.setText('Reposition Pivot')
        primary(owner.apply_pivot_button, 'Rotate Around Pivot')
    elif key == 'ikfk':
        owner.switch_fk_to_ik_button.setText('Switch to IK')
        owner.switch_ik_to_fk_button.setText('Switch to FK')
        owner.load_profile_button.clicked.connect(lambda _checked=False, section=owner._task_sections[1]: section.setExpanded(False))
    owner.setMinimumWidth(320)
    for form in owner.findChildren(QtWidgets.QFormLayout):
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
    for field in owner.findChildren(QtWidgets.QLineEdit):
        field.setMinimumWidth(0)
        field.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
    for combo in owner.findChildren(QtWidgets.QComboBox):
        combo.setMinimumContentsLength(0)
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    for group in owner.findChildren(QtWidgets.QGroupBox):
        if not group.findChildren(QtWidgets.QWidget):
            group.hide()
    # Narrow docks must not inherit a button's desktop-width minimum.
    for widget in owner.findChildren(QtWidgets.QPushButton):
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
    for label in owner.findChildren(QtWidgets.QLabel):
        pixmap = label.pixmap()
        if pixmap is None or pixmap.isNull():
            label.setWordWrap(True)


def form_rows(owner, form, fields):
    """Move complete form rows, including their labels."""
    result = QtWidgets.QFormLayout()
    result.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
    for field in fields:
        row, role = form.getWidgetPosition(field)
        if row < 0:
            raise ValueError('Missing form field')
        taken = form.takeRow(row)
        label = taken.labelItem.widget() if taken.labelItem else None
        widget = taken.fieldItem.widget()
        if label:
            result.addRow(label, widget)
        else:
            result.addRow(widget)
    return result


def apply_extra(owner, key, local):
    if key == 'reference':
        primary(owner.package_button, 'Create Scene ZIP')
        options = action_grid(owner, [owner.save_scene_box, owner.references_box, owner.external_box, owner.relative_box])
        owner._task_sections = arrange(owner, local['layout'], [
            ('Create Scene ZIP', True, [local['output_row'], local['name_row'], owner.package_button, owner.open_folder_button]),
            ('Files to include', True, [owner.refresh_button, owner.files_table]),
            ('Packaging options', False, [options]),
            ('Scene cleanup (optional)', False, [local['cleanup_group']]),
            ('Help', False, [local['intro']]),
        ])
        local['package_group'].hide()
        owner.files_table.setMaximumHeight(260)
    elif key == 'onion':
        form = local['form_layout']
        essentials = form_rows(owner, form, [owner.past_spin, owner.future_spin, owner.frame_step_spin])
        details = form_rows(owner, form, [owner.display_mode_combo, owner.opacity_spin, owner.falloff_spin, owner.past_color_button, owner.future_color_button, owner.auto_update_check, owner.full_fidelity_scrub_check])
        primary(owner.attach_button, 'Use Selection')
        owner.onion_enabled = QtWidgets.QCheckBox('Ghost preview enabled')
        owner.onion_enabled.setToolTip('Off hides the current preview while keeping its attached rigs. On refreshes it.')
        def toggle(enabled):
            if enabled:
                owner._apply_settings()
                success, message = owner.controller.manual_refresh()
                if success:
                    owner.controller._register_callbacks()
                owner._populate_from_controller()
                owner._set_status(message, success)
                owner.onion_enabled.blockSignals(True)
                owner.onion_enabled.setChecked(success)
                owner.onion_enabled.blockSignals(False)
            else:
                owner.controller.detach(clear_attachment=False)
                owner._set_status('Ghost preview hidden. Attached rigs are retained.', True)
        owner.onion_enabled.toggled.connect(toggle)
        def attached():
            owner.onion_enabled.blockSignals(True)
            owner.onion_enabled.setChecked(bool(owner.controller.attached_roots))
            owner.onion_enabled.blockSignals(False)
        owner.attach_button.clicked.connect(attached)
        owner.add_button.clicked.connect(attached)
        owner.clear_button.clicked.connect(attached)
        arrange(owner, local['main_layout'], [
            ('Ghost preview', True, [owner.attach_button, essentials, owner.onion_enabled]),
            ('Refresh and selection', True, [owner.add_button, owner.refresh_button, owner.clear_button]),
            ('Appearance and performance', False, [details]),
            ('Help', False, [local['description']]),
        ])
    elif key == 'smear':
        form = local['form']
        essential = form_rows(owner, form, [owner.name_edit, owner.range_start_spin, owner.range_end_spin])
        options = form_rows(owner, form, [owner.prev_spin, owner.next_spin, owner.strength_spin, owner.mode_combo, owner.visibility_check])
        primary(owner.create_button, 'Create Smear')
        owner.edit_state_label = QtWidgets.QLabel('Select a saved smear to edit it.')
        arrange(owner, local['layout'], [
            ('1. Mesh and frame range', True, [owner.selected_label, owner.refresh_button, essential]),
            ('2. Create and edit', True, [owner.create_button, owner.edit_state_label, owner.edit_button, owner.finish_edit_button]),
            ('Smear options', False, [options]),
            ('Saved smears', True, [local['saved_label'], owner.saved_list, owner.select_button, owner.apply_range_button]),
            ('Export and delete', False, [owner.export_button, owner.delete_button]),
            ('Help', False, [local['help_label']]),
        ])
    elif key == 'notes':
        form = local['form']
        # Keep title, range and colour in labelled two-column rows.
        items = [form.takeAt(0) for _ in range(form.count())]
        for index, item in enumerate(items):
            if item.widget():
                form.addWidget(item.widget(), index // 2, index % 2)
        owner.overlay_enabled_check.setText('Show note ranges on Maya timeline')
        owner.update_button.setText('Save Changes')
        primary(owner.add_button, 'Add Note')
        local['range_row'].removeWidget(owner.add_button)
        local['range_row'].removeWidget(owner.update_button)
        local['range_row'].removeWidget(owner.delete_button)
        actions = action_grid(owner, [owner.add_button, owner.update_button, owner.delete_button])
        local['notes_layout'].insertLayout(2, actions)
        details = section(owner, 'Range and automatic updating', [local['range_row']], False)
        local['notes_layout'].insertWidget(3, details)
        owner.auto_update_note_check.setText('Automatically save edits to selected note')
        owner.auto_update_note_check.setToolTip('When checked, changing note fields writes to the selected scene note automatically.')
        files = section(owner, 'Import / Export', [local['file_row']], False)
        local['notes_layout'].addWidget(files)
        def sync_note():
            selected = bool(owner.notes_list.selectedItems())
            owner.update_button.setEnabled(selected)
            owner.delete_button.setEnabled(selected)
        owner.notes_list.itemSelectionChanged.connect(sync_note)
        sync_note()
    elif key == 'scene':
        root = local['section_content_layout']
        for row in owner.findChildren(QtWidgets.QHBoxLayout):
            if row.count() >= 3:
                row.setDirection(QtWidgets.QBoxLayout.TopToBottom)
        local['game_mode_top_row'].setDirection(QtWidgets.QBoxLayout.TopToBottom)
        checks = local['game_mode_checks']
        entries = [checks.takeAt(0) for _ in range(checks.count())]
        for index, item in enumerate(entries):
            if item.widget(): checks.addWidget(item.widget(), index, 0)
        owner.keep_toolbar_extras_on_hide_check.setText('Keep floating tools when Aminate hides')
        old_groups = [root.itemAt(i).widget() for i in range(root.count())]
        offsets = QtWidgets.QFormLayout()
        for text, field in [('Camera height', owner.camera_height_offset_spin), ('Camera distance', owner.camera_dolly_offset_spin)]:
            detach(owner, field); offsets.addRow(text, field)
        teacher_offset = QtWidgets.QFormLayout()
        detach(owner, owner.teacher_rig_offset_spin); teacher_offset.addRow('Rig copy offset X', owner.teacher_rig_offset_spin)
        prefs = QtWidgets.QPushButton('Window shortcuts and opacity…')
        prefs.clicked.connect(lambda: open_module('customization'))
        groups = [
            ('Scene setup', True, [owner.load_textures_button, owner.recover_autosave_button, local['self.game_mode_group'] if 'self.game_mode_group' in local else owner.game_mode_group, owner.render_env_button, owner.delete_render_env_button, local['camera_row']]),
            ('Animation', False, [action_grid(owner,[owner.auto_key_button, owner.auto_snap_button]), local['retime_row'], local['snap_row'], local['layer_row'], local['animation_layers_group'], local['blocking_options_row']]),
            ('Teaching', False, [owner.duplicate_teacher_rig_button, owner.delete_teacher_rig_button, teacher_offset, local['teacher_log_group'], local['notes_page']]),
            ('Floating windows', False, [owner.open_tween_machine_button, owner.open_floating_channel_box_button, owner.open_floating_graph_button, prefs]),
            ('Camera and security options', False, [offsets, owner.disable_security_popups_button]),
            ('Help', False, [local['help_page']]),
        ]
        arrange(owner, root, groups)
        for group in old_groups:
            if group:
                root.removeWidget(group); group.hide()
    elif key == 'quick_start':
        grid = QtWidgets.QGridLayout()
        choices = [('Animate', 'toolkit_bar'), ('Fix motion', 'rotation_doctor'), ('Draw feedback', 'animators_pencil'), ('Prepare / export', 'rig_scale')]
        for i, (title, alias) in enumerate(choices):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(lambda _checked=False, target=alias: owner._set_initial_tab(target))
            grid.addWidget(button, i//2, i%2)
        local['layout'].insertLayout(1, grid)
    elif key == 'skin_tasks':
        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName('aminateSkinTaskTabs')
        for title, panel in [('Copy Skin Weights', owner.skin_transfer_panel), ('Fix Mesh Transforms', owner.skin_panel)]:
            detach(owner, panel); tabs.addTab(panel, title)
        local['freeze_heading'].hide(); local['transfer_heading'].hide()
        local['layout'].addWidget(tabs, 1)
    elif key == 'channel':
        opacity = QtWidgets.QDoubleSpinBox()
        opacity.setRange(0.3, 1.0); opacity.setSingleStep(0.05)
        import maya_floating_channel_box as floating
        opacity.setValue(floating.get_channel_opacity())
        opacity.setAccessibleName('Window opacity')
        opacity.valueChanged.connect(lambda value: (floating.set_channel_opacity(value), owner.setWindowOpacity(value)))
        pin = QtWidgets.QCheckBox('Pin selection')
        pin.setToolTip('Keep the current controls in this Channel Box when Maya selection changes.')
        owner.pin_selection_check = pin
        row = QtWidgets.QHBoxLayout()
        row.addWidget(pin)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel('Opacity'))
        row.addWidget(opacity)
        local['layout'].insertLayout(1, row)
        pin.toggled.connect(owner.refresh)
    if key == 'notes':
        for row in owner.findChildren(QtWidgets.QHBoxLayout):
            if row.count() >= 3: row.setDirection(QtWidgets.QBoxLayout.TopToBottom)
    apply(owner, key, local)


def open_module(alias):
    import maya_timing_tools
    return maya_timing_tools._open_workflow_tab(alias)


DEFAULT_PINS = ('toolkit_bar', 'scene_helpers', 'control_picker', 'animators_pencil', 'history_timeline', 'rotation_doctor')
PIN_OPTION = 'AminateToolbarPinnedTools'
_session_pins = None


def toolbar_pins():
    global _session_pins
    try:
        import json
        import maya.cmds as cmds
        if cmds.optionVar(exists=PIN_OPTION):
            value = json.loads(cmds.optionVar(query=PIN_OPTION))
            if isinstance(value, list):
                return value
    except (ImportError, ValueError, TypeError, RuntimeError):
        pass
    return list(_session_pins if _session_pins is not None else DEFAULT_PINS)


def save_toolbar_pins(pins):
    global _session_pins
    _session_pins = list(pins)
    try:
        import json
        import maya.cmds as cmds
        cmds.optionVar(stringValue=(PIN_OPTION, json.dumps(_session_pins)))
    except ImportError:
        pass
    import maya_timing_tools
    for bar in list(maya_timing_tools.GLOBAL_TIMELINE_BAR_WIDGETS):
        for alias, button in getattr(bar, '_workflow_buttons', {}).items():
            button.setVisible(alias in _session_pins)


def add_toolbar_menu(bar, layout):
    import maya_aminate_icon_manifest as manifest
    pins = toolbar_pins()
    for alias, button in bar._workflow_buttons.items():
        button.setVisible(alias in pins)
    menu_button = QtWidgets.QToolButton()
    menu_button.setText('More tools')
    menu_button.setAccessibleName('All Aminate tools')
    menu_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    menu = QtWidgets.QMenu(menu_button)
    for item in manifest.workflow_toolbar_tools():
        if item['tab'] == 'reference_manager':
            continue
        action = menu.addAction(item['tooltip'].split(':', 1)[0])
        action.triggered.connect(lambda _checked=False, alias=item['tab']: bar._run_workflow_button(alias))
    menu.addSeparator()
    menu.addAction('Customise toolbar…', lambda: open_module('customization'))
    menu_button.setMenu(menu)
    layout.addWidget(menu_button)
    bar.all_tools_button = menu_button


def build_customization(owner, local):
    import maya_aminate_icon_manifest as manifest
    import maya_timing_tools as timing
    import maya_floating_channel_box as floating
    root = local['layout']
    colour_grid = local['form']
    for row in range(colour_grid.rowCount()):
        item = colour_grid.itemAtPosition(row, 3)
        if item and item.widget():
            item.widget().hide()
    for edit in owner.hex_edits.values():
        edit.setMinimumWidth(80)
    theme = owner.findChild(QtWidgets.QGroupBox, 'aminateCustomizationThemeGroup')
    if theme is None:
        theme = next(g for g in owner.findChildren(QtWidgets.QGroupBox) if g.title() == 'Aminate Theme')
    tooltip = owner.findChild(QtWidgets.QGroupBox, 'aminateCustomizationTooltipPreviewGroup')
    toolbar = QtWidgets.QWidget()
    toolbar_layout = QtWidgets.QVBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(0, 0, 0, 0)
    hint = QtWidgets.QLabel('Pin frequent tools. Every module remains available in More tools. Both ZIP buttons stay visible.')
    hint.setWordWrap(True); toolbar_layout.addWidget(hint)
    grid = QtWidgets.QGridLayout(); checks = {}
    pins = toolbar_pins()
    for item in manifest.workflow_toolbar_tools():
        alias = item['tab']
        if alias == 'reference_manager': continue
        check = QtWidgets.QCheckBox(item['tooltip'].split(':', 1)[0])
        check.setChecked(alias in pins)
        grid.addWidget(check, len(checks)//2, len(checks)%2)
        checks[alias] = check
    toolbar_layout.addLayout(grid)
    preview = QtWidgets.QLabel(); preview.setWordWrap(True); toolbar_layout.addWidget(preview)
    def changed():
        chosen = [alias for alias, check in checks.items() if check.isChecked()]
        save_toolbar_pins(chosen)
        preview.setText('Pinned: ' + (', '.join(checks[a].text() for a in chosen) or 'none (use More tools)'))
    for check in checks.values(): check.toggled.connect(changed)
    reset_pins = QtWidgets.QPushButton('Reset toolbar favourites')
    def reset():
        for alias, check in checks.items():
            check.blockSignals(True); check.setChecked(alias in DEFAULT_PINS); check.blockSignals(False)
        changed()
    reset_pins.clicked.connect(reset); toolbar_layout.addWidget(reset_pins)
    preview.setText('Pinned: ' + ', '.join(check.text() for check in checks.values() if check.isChecked()))
    shortcuts = QtWidgets.QWidget(); shortcuts_layout = QtWidgets.QVBoxLayout(shortcuts)
    shortcuts_layout.setContentsMargins(0, 0, 0, 0)
    # Use the existing controller setters so collision checks and registration stay intact.
    def get_controller():
        import maya_dynamic_parent_pivot as workflow
        current = getattr(workflow, 'GLOBAL_CONTROLLER', None)
        if current is not None:
            return current.get_timing_controller()
        if not hasattr(owner, '_window_preferences_controller'):
            owner._window_preferences_controller = timing.MayaTimingToolsController()
        return owner._window_preferences_controller
    definitions = [
        ('Tween Machine', lambda: timing.MayaTimingToolsController.get_tween_machine_hotkey(None), 'set_tween_machine_hotkey', lambda: timing.MayaTimingToolsController.get_tween_machine_opacity(None), 'set_tween_machine_opacity'),
        ('Channel Box', floating.get_hotkey, 'set_floating_channel_box_hotkey', floating.get_channel_opacity, 'set_floating_channel_box_opacity'),
        ('Graph Editor', floating.get_graph_editor_hotkey, 'set_floating_graph_editor_hotkey', floating.get_graph_editor_opacity, 'set_floating_graph_editor_opacity'),
    ]
    for title, hotkey_get, hotkey_set, opacity_get, opacity_set in definitions:
        row = QtWidgets.QFormLayout(); row.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        field = QtWidgets.QLineEdit(hotkey_get())
        opacity = QtWidgets.QDoubleSpinBox(); opacity.setRange(.3, 1.0); opacity.setSingleStep(.05); opacity.setValue(opacity_get())
        button = QtWidgets.QPushButton('Apply ' + title)
        row.addRow(title + ' shortcut', field); row.addRow('Opacity', opacity); row.addRow(button)
        def apply_settings(_checked=False, edit=field, value=opacity, key_method=hotkey_set, opacity_method=opacity_set):
            controller = get_controller()
            ok, message = getattr(controller, key_method)(edit.text())
            if ok: ok, message = getattr(controller, opacity_method)(value.value())
            owner.status_label.setText(message)
        button.clicked.connect(apply_settings)
        shortcuts_layout.addLayout(row)
    reset_theme = QtWidgets.QPushButton('Reset appearance theme')
    reset_theme.clicked.connect(lambda: owner.theme_combo.setCurrentIndex(0))
    theme.layout().addWidget(reset_theme)
    owner._task_sections = arrange(owner, root, [
        ('Appearance', True, [theme, local['color_group'], local['button_row']]),
        ('Toolbar', False, [toolbar]),
        ('Window shortcuts and opacity', False, [shortcuts]),
        ('Tooltips', False, [tooltip]),
        ('Help', False, [local['intro']]),
    ])
    apply(owner, 'customization', local)
