from __future__ import absolute_import, division, print_function

import os
import re

try:
    import maya.cmds as cmds

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    MAYA_AVAILABLE = False

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except Exception:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except Exception:
        QtCore = QtGui = QtWidgets = None

import maya_skinning_cleanup as skin_cleanup
import maya_timing_tools
import maya_aminate_theme


WINDOW_OBJECT_NAME = "aminateCustomizationWindow"
WORKSPACE_CONTROL_NAME = WINDOW_OBJECT_NAME + "WorkspaceControl"
GLOBAL_WINDOW = None
GLOBAL_CONTROLLER = None
FOLLOW_AMIR_URL = "https://followamir.com"
DEFAULT_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=2U2GXSKFJKJCA"
DONATE_URL = os.environ.get("AMIR_PAYPAL_DONATE_URL") or os.environ.get("AMIR_DONATE_URL") or DEFAULT_DONATE_URL

OPTION_PREFIX = "AminateCustomization"
COLOR_FIELDS = [
    {
        "key": "keyframe_red_bar",
        "label": "Keyframe Red Bar",
        "default": "#EF4444",
        "targets": ("timeSliderCurrentFrame", "timeSliderTickDrawSpecial", "timeSliderTickDraw"),
        "help": "Main red frame marker / key emphasis color where Maya exposes that display slot.",
    },
    {
        "key": "timeline_drag_highlight",
        "label": "Timeline Drag Highlight",
        "default": "#38BDF8",
        "targets": ("timeSliderHighlight", "timeSliderRange", "timeSliderBookmark"),
        "help": "Highlighted frame range and Aminate timeline overlay accent.",
    },
    {
        "key": "timeline_note_range",
        "label": "Timeline Note Range",
        "default": "#F2CC8F",
        "targets": (),
        "help": "Default Aminate Timeline Notes range color.",
    },
    {
        "key": "x_tangent",
        "label": "X Tangents",
        "default": "#EF4444",
        "targets": ("graphEditorCurveX", "graphEditorTangentX", "xAxis"),
        "help": "Graph editor X-axis tangent and curve accent when available.",
    },
    {
        "key": "y_tangent",
        "label": "Y Tangents",
        "default": "#22C55E",
        "targets": ("graphEditorCurveY", "graphEditorTangentY", "yAxis"),
        "help": "Graph editor Y-axis tangent and curve accent when available.",
    },
    {
        "key": "z_tangent",
        "label": "Z Tangents",
        "default": "#3B82F6",
        "targets": ("graphEditorCurveZ", "graphEditorTangentZ", "zAxis"),
        "help": "Graph editor Z-axis tangent and curve accent when available.",
    },
    {
        "key": "selected_curve",
        "label": "Selected Curve",
        "default": "#FACC15",
        "targets": ("graphEditorCurveSelected", "graphEditorKeySelected", "activeCurve"),
        "help": "Selected curve or selected key accent where Maya exposes that display slot.",
    },
]


_style_donate_button = skin_cleanup._style_donate_button
_open_external_url = skin_cleanup._open_external_url
_maya_main_window = skin_cleanup._maya_main_window


def _option_name(key):
    return "{0}_{1}".format(OPTION_PREFIX, key)


def _normalize_hex(value, fallback="#FFFFFF"):
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    if not re.match(r"^#[0-9a-fA-F]{6}$", text):
        text = fallback
    return text.upper()


def _hex_to_rgb01(color_hex):
    color_hex = _normalize_hex(color_hex)
    return (
        int(color_hex[1:3], 16) / 255.0,
        int(color_hex[3:5], 16) / 255.0,
        int(color_hex[5:7], 16) / 255.0,
    )


def _field_by_key(key):
    for field in COLOR_FIELDS:
        if field["key"] == key:
            return field
    raise KeyError(key)


def _save_option_var_string(option_name, value):
    if not cmds:
        return
    try:
        cmds.optionVar(stringValue=(option_name, value or ""))
    except Exception:
        pass


def _load_option_var_string(option_name, default):
    if not cmds:
        return default
    try:
        if cmds.optionVar(exists=option_name):
            return cmds.optionVar(query=option_name)
    except Exception:
        pass
    return default


def default_settings():
    return {field["key"]: field["default"] for field in COLOR_FIELDS}


class AminateCustomizationController(object):
    def __init__(self):
        self._last_apply_report = {}

    def settings(self):
        values = {}
        for field in COLOR_FIELDS:
            values[field["key"]] = _normalize_hex(
                _load_option_var_string(_option_name(field["key"]), field["default"]),
                field["default"],
            )
        return values

    def set_color(self, key, color_hex, apply_now=True):
        field = _field_by_key(key)
        color_hex = _normalize_hex(color_hex, field["default"])
        _save_option_var_string(_option_name(key), color_hex)
        report = self.apply_colors() if apply_now else {"applied": [], "warnings": []}
        return True, "{0} set to {1}.".format(field["label"], color_hex), report

    def set_settings(self, settings, apply_now=True):
        for field in COLOR_FIELDS:
            if field["key"] in settings:
                _save_option_var_string(
                    _option_name(field["key"]),
                    _normalize_hex(settings.get(field["key"]), field["default"]),
                )
        report = self.apply_colors() if apply_now else {"applied": [], "warnings": []}
        return True, "Customization colors saved.", report

    def reset_defaults(self, apply_now=True):
        for field in COLOR_FIELDS:
            _save_option_var_string(_option_name(field["key"]), field["default"])
        report = self.apply_colors() if apply_now else {"applied": [], "warnings": []}
        return True, "Customization colors reset.", report

    def timeline_note_default_color(self):
        return self.settings().get("timeline_note_range", _field_by_key("timeline_note_range")["default"])

    def apply_colors(self):
        settings = self.settings()
        applied = []
        warnings = []
        if not cmds:
            report = {"applied": applied, "warnings": ["Maya commands are not available."]}
            self._last_apply_report = report
            return report
        try:
            if cmds.about(batch=True):
                report = {
                    "applied": applied,
                    "warnings": ["Native Maya timeline and Graph Editor colors can only be applied in interactive Maya; Aminate settings were saved."],
                }
                self._last_apply_report = report
                return report
        except Exception:
            pass
        for field in COLOR_FIELDS:
            color_hex = settings[field["key"]]
            red, green, blue = _hex_to_rgb01(color_hex)
            for target in field.get("targets") or ():
                try:
                    cmds.displayRGBColor(target, red, green, blue)
                    applied.append(target)
                except Exception:
                    continue
        if not applied:
            warnings.append("Maya did not expose native timeline or graph-editor display slots in this session; Aminate settings were still saved.")
        report = {"applied": sorted(set(applied)), "warnings": warnings}
        self._last_apply_report = report
        return report

    def last_apply_report(self):
        return dict(self._last_apply_report)

    def toolkit_hover_settings(self):
        return maya_timing_tools.toolkit_hover_settings()

    def set_toolkit_hover_settings(self, icon_pixels=None, opacity=None, wording_mode=None):
        settings = maya_timing_tools.set_toolkit_hover_settings(
            icon_pixels=icon_pixels,
            opacity=opacity,
            wording_mode=wording_mode,
        )
        return True, "Toolkit tooltip preview saved.", settings

    def reset_toolkit_hover_settings(self):
        settings = maya_timing_tools.reset_toolkit_hover_settings()
        return True, "Toolkit tooltip preview reset.", settings

    def shutdown(self):
        pass


if QtWidgets is not None:
    class ColorButton(QtWidgets.QPushButton):
        colorChanged = QtCore.Signal(str) if hasattr(QtCore, "Signal") else QtCore.pyqtSignal(str)

        def __init__(self, color_hex="#FFFFFF", parent=None):
            super(ColorButton, self).__init__(parent)
            self._color = _normalize_hex(color_hex)
            self.setMinimumWidth(72)
            self.clicked.connect(self._pick_color)
            self.set_color(self._color)

        def color(self):
            return self._color

        def set_color(self, color_hex):
            self._color = _normalize_hex(color_hex)
            self.setText(self._color)
            self.setStyleSheet(
                "QPushButton { background-color: %s; color: #111111; border: 1px solid #202020; padding: 5px 8px; }"
                "QPushButton:hover { border-color: #FFFFFF; }" % self._color
            )

        def _pick_color(self):
            picked = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._color), self, "Pick Aminate color")
            if picked.isValid():
                self.set_color(picked.name().upper())
                self.colorChanged.emit(self._color)


    class AminateCustomizationWindow(QtWidgets.QWidget):
        def __init__(self, controller=None, parent=None, show_footer=True):
            super(AminateCustomizationWindow, self).__init__(parent)
            self.controller = controller or AminateCustomizationController()
            self.show_footer = bool(show_footer)
            self.color_buttons = {}
            self.hex_edits = {}
            self.status_label = None
            self.tooltip_preview_card = None
            self.theme_combo = None
            self.theme_preview_label = None
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("Aminate Customization")
            self.setMinimumSize(360, 420)
            self.resize(620, 720)
            self._build_ui()
            self._load_settings()

        def _build_ui(self):
            outer_layout = QtWidgets.QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            scroll = QtWidgets.QScrollArea(self)
            scroll.setObjectName("aminateCustomizationContentScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumWidth(0)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            content = QtWidgets.QWidget()
            content.setMinimumWidth(0)
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)
            intro = QtWidgets.QLabel("Pick the animation colors once, then apply them to Aminate overlays and any native Maya timeline or Graph Editor color slots Maya exposes.")
            intro.setWordWrap(True)
            layout.addWidget(intro)
            self._build_theme_selector(layout)
            color_group = QtWidgets.QGroupBox("Animation Colors")
            color_group.setObjectName("aminateCustomizationColorGroup")
            form = QtWidgets.QGridLayout(color_group)
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(6)
            form.addWidget(QtWidgets.QLabel("Area"), 0, 0)
            form.addWidget(QtWidgets.QLabel("Color"), 0, 1)
            form.addWidget(QtWidgets.QLabel("Hex"), 0, 2)
            form.addWidget(QtWidgets.QLabel("What It Changes"), 0, 3)
            for row, field in enumerate(COLOR_FIELDS, start=1):
                label = QtWidgets.QLabel(field["label"])
                label.setToolTip(field["help"])
                button = ColorButton(field["default"])
                button.setObjectName("aminateCustomizationColorButton_{0}".format(field["key"]))
                edit = QtWidgets.QLineEdit(field["default"])
                edit.setObjectName("aminateCustomizationHexEdit_{0}".format(field["key"]))
                edit.setMaximumWidth(92)
                help_label = QtWidgets.QLabel(field["help"])
                help_label.setWordWrap(True)
                form.addWidget(label, row, 0)
                form.addWidget(button, row, 1)
                form.addWidget(edit, row, 2)
                form.addWidget(help_label, row, 3)
                self.color_buttons[field["key"]] = button
                self.hex_edits[field["key"]] = edit
                button.colorChanged.connect(lambda color, key=field["key"]: self._sync_edit_from_button(key, color))
                edit.editingFinished.connect(lambda key=field["key"]: self._sync_button_from_edit(key))
            layout.addWidget(color_group)
            button_row = QtWidgets.QHBoxLayout()
            self.apply_button = QtWidgets.QPushButton("Apply Colors")
            self.apply_button.setObjectName("aminateCustomizationApplyButton")
            self.apply_button.setToolTip("Save these colors and apply every supported Maya/Aminate color slot.")
            self.reset_button = QtWidgets.QPushButton("Reset")
            self.reset_button.setObjectName("aminateCustomizationResetButton")
            self.reset_button.setToolTip("Restore Aminate's default animation colors.")
            button_row.addWidget(self.apply_button)
            button_row.addWidget(self.reset_button)
            button_row.addStretch(1)
            layout.addLayout(button_row)
            self._build_toolkit_tooltip_preview(layout)
            self.status_label = QtWidgets.QLabel("")
            self.status_label.setObjectName("aminateCustomizationStatusLabel")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            if self.show_footer:
                footer = QtWidgets.QHBoxLayout()
                self.brand_label = QtWidgets.QLabel('Built by Amir. Follow Amir at <a href="{0}">followamir.com</a>.'.format(FOLLOW_AMIR_URL))
                self.brand_label.setOpenExternalLinks(False)
                self.brand_label.linkActivated.connect(lambda _url: _open_external_url(FOLLOW_AMIR_URL))
                footer.addWidget(self.brand_label, 1)
                self.donate_button = QtWidgets.QPushButton("Donate")
                _style_donate_button(self.donate_button)
                self.donate_button.clicked.connect(lambda: _open_external_url(DONATE_URL))
                footer.addWidget(self.donate_button)
                layout.addLayout(footer)
            self.apply_button.clicked.connect(self._apply)
            self.reset_button.clicked.connect(self._reset)
            scroll.setWidget(content)
            outer_layout.addWidget(scroll)

        def _build_theme_selector(self, parent_layout):
            group = QtWidgets.QGroupBox("Aminate Theme")
            group.setObjectName("aminateCustomizationThemeGroup")
            group_layout = QtWidgets.QVBoxLayout(group)
            group_layout.setContentsMargins(10, 10, 10, 10)
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel("Theme")
            label.setObjectName("aminateCustomizationThemeLabel")
            self.theme_combo = QtWidgets.QComboBox()
            self.theme_combo.setObjectName("aminateCustomizationThemeCombo")
            self.theme_combo.setToolTip("Choose the Aminate workbench contrast treatment. The change applies immediately and is remembered in Maya.")
            self.theme_combo.setMinimumWidth(0)
            self.theme_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            for descriptor in maya_aminate_theme.available_themes():
                self.theme_combo.addItem(descriptor["name"], descriptor["name"])
            row.addWidget(label)
            row.addWidget(self.theme_combo, 1)
            group_layout.addLayout(row)
            helper = QtWidgets.QLabel(
                "Maya Graphite stays close to the host UI. Studio Contrast deepens the surfaces without per-tool colours or accent borders."
            )
            helper.setObjectName("aminateCustomizationThemeHelper")
            helper.setWordWrap(True)
            group_layout.addWidget(helper)
            self.theme_preview_label = QtWidgets.QLabel()
            self.theme_preview_label.setObjectName("aminateCustomizationThemePreview")
            self.theme_preview_label.setWordWrap(True)
            group_layout.addWidget(self.theme_preview_label)
            parent_layout.addWidget(group)
            self.theme_combo.currentIndexChanged.connect(self._theme_changed)

        def _load_theme_settings(self):
            if self.theme_combo is None:
                return
            name = maya_aminate_theme.load_theme_name()
            index = self.theme_combo.findData(name)
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(max(0, index))
            self.theme_combo.blockSignals(False)
            self._refresh_theme_preview(name)

        def _refresh_theme_preview(self, theme_name=None):
            if self.theme_preview_label is None:
                return
            name = theme_name or str(self.theme_combo.currentData() or maya_aminate_theme.DEFAULT_THEME_NAME)
            descriptor = next((item for item in maya_aminate_theme.available_themes() if item["name"] == name), None)
            self.theme_preview_label.setText((descriptor or {}).get("preview", ""))

        def _theme_changed(self, _index):
            if self.theme_combo is None:
                return
            name = maya_aminate_theme.set_theme_name(self.theme_combo.currentData())
            self._refresh_theme_preview(name)
            root = self
            while root is not None:
                try:
                    if root.objectName() == "aminateWindow":
                        apply_theme = getattr(root, "apply_aminate_theme", None)
                        if callable(apply_theme):
                            apply_theme(name)
                        else:
                            maya_aminate_theme.apply_theme_to_window(root, name)
                        break
                    root = root.parentWidget()
                except Exception:
                    break
            if self.status_label is not None:
                self.status_label.setText("Aminate theme set to {0}.".format(name))

        def _build_toolkit_tooltip_preview(self, parent_layout):
            group = QtWidgets.QGroupBox("Toolkit Bar Tooltip Preview")
            group.setObjectName("aminateCustomizationTooltipPreviewGroup")
            group_layout = QtWidgets.QVBoxLayout(group)
            group_layout.setContentsMargins(10, 10, 10, 10)
            group_layout.setSpacing(8)
            controls = QtWidgets.QGridLayout()
            controls.setHorizontalSpacing(8)
            controls.setVerticalSpacing(6)
            self.tooltip_icon_size_spin = QtWidgets.QSpinBox()
            self.tooltip_icon_size_spin.setObjectName("aminateCustomizationTooltipIconSizeSpin")
            self.tooltip_icon_size_spin.setRange(40, 96)
            self.tooltip_icon_size_spin.setSingleStep(4)
            self.tooltip_icon_size_spin.setToolTip("How large the icon appears in the Toolkit Bar hover card.")
            self.tooltip_opacity_spin = QtWidgets.QDoubleSpinBox()
            self.tooltip_opacity_spin.setObjectName("aminateCustomizationTooltipOpacitySpin")
            self.tooltip_opacity_spin.setRange(0.50, 1.0)
            self.tooltip_opacity_spin.setDecimals(2)
            self.tooltip_opacity_spin.setSingleStep(0.05)
            self.tooltip_opacity_spin.setToolTip("How see-through the Toolkit Bar hover card is.")
            self.tooltip_wording_combo = QtWidgets.QComboBox()
            self.tooltip_wording_combo.setObjectName("aminateCustomizationTooltipWordingCombo")
            self.tooltip_wording_combo.addItem("Simple", "simple")
            self.tooltip_wording_combo.addItem("Kid Mode", "kid")
            self.tooltip_wording_combo.addItem("Technical", "technical")
            self.tooltip_wording_combo.setToolTip("Choose how Toolkit Bar hover cards explain each button.")
            controls.addWidget(QtWidgets.QLabel("Icon Size"), 0, 0)
            controls.addWidget(self.tooltip_icon_size_spin, 0, 1)
            controls.addWidget(QtWidgets.QLabel("Opacity"), 0, 2)
            controls.addWidget(self.tooltip_opacity_spin, 0, 3)
            controls.addWidget(QtWidgets.QLabel("Wording"), 1, 0)
            controls.addWidget(self.tooltip_wording_combo, 1, 1, 1, 3)
            group_layout.addLayout(controls)

            self.tooltip_preview_card = QtWidgets.QFrame()
            self.tooltip_preview_card.setObjectName("aminateCustomizationTooltipPreviewCard")
            preview_layout = QtWidgets.QHBoxLayout(self.tooltip_preview_card)
            preview_layout.setContentsMargins(10, 9, 10, 9)
            preview_layout.setSpacing(10)
            self.tooltip_preview_icon = QtWidgets.QLabel()
            self.tooltip_preview_icon.setObjectName("aminateCustomizationTooltipPreviewIcon")
            self.tooltip_preview_icon.setAlignment(QtCore.Qt.AlignCenter)
            preview_layout.addWidget(self.tooltip_preview_icon)
            text_layout = QtWidgets.QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(3)
            self.tooltip_preview_title = QtWidgets.QLabel("Combine Freeze Pivot")
            self.tooltip_preview_title.setObjectName("aminateCustomizationTooltipPreviewTitle")
            self.tooltip_preview_description = QtWidgets.QLabel("")
            self.tooltip_preview_description.setObjectName("aminateCustomizationTooltipPreviewDescription")
            self.tooltip_preview_description.setWordWrap(True)
            text_layout.addWidget(self.tooltip_preview_title)
            text_layout.addWidget(self.tooltip_preview_description)
            preview_layout.addLayout(text_layout, 1)
            group_layout.addWidget(self.tooltip_preview_card)

            action_row = QtWidgets.QHBoxLayout()
            self.apply_tooltip_button = QtWidgets.QPushButton("Apply Tooltip Style")
            self.apply_tooltip_button.setObjectName("aminateCustomizationApplyTooltipStyleButton")
            self.apply_tooltip_button.setToolTip("Save these hover-card settings and refresh any open Toolkit Bar.")
            self.reset_tooltip_button = QtWidgets.QPushButton("Reset Tooltip Style")
            self.reset_tooltip_button.setObjectName("aminateCustomizationResetTooltipStyleButton")
            self.reset_tooltip_button.setToolTip("Restore Aminate's default Toolkit Bar hover-card style.")
            action_row.addWidget(self.apply_tooltip_button)
            action_row.addWidget(self.reset_tooltip_button)
            action_row.addStretch(1)
            group_layout.addLayout(action_row)
            parent_layout.addWidget(group)

            self.apply_tooltip_button.clicked.connect(self._apply_toolkit_tooltip_settings)
            self.reset_tooltip_button.clicked.connect(self._reset_toolkit_tooltip_settings)
            self.tooltip_icon_size_spin.valueChanged.connect(self._refresh_toolkit_tooltip_preview)
            self.tooltip_opacity_spin.valueChanged.connect(self._refresh_toolkit_tooltip_preview)
            self.tooltip_wording_combo.currentIndexChanged.connect(self._refresh_toolkit_tooltip_preview)
            self.tooltip_icon_size_spin.valueChanged.connect(self._apply_toolkit_tooltip_settings)
            self.tooltip_opacity_spin.valueChanged.connect(self._apply_toolkit_tooltip_settings)
            self.tooltip_wording_combo.currentIndexChanged.connect(self._apply_toolkit_tooltip_settings)

        def _load_settings(self):
            self._load_theme_settings()
            settings = self.controller.settings()
            for key, value in settings.items():
                if key in self.color_buttons:
                    self.color_buttons[key].set_color(value)
                if key in self.hex_edits:
                    self.hex_edits[key].setText(value)
            self._load_toolkit_tooltip_settings()

        def _load_toolkit_tooltip_settings(self):
            settings = self.controller.toolkit_hover_settings()
            self.tooltip_icon_size_spin.blockSignals(True)
            self.tooltip_opacity_spin.blockSignals(True)
            self.tooltip_wording_combo.blockSignals(True)
            self.tooltip_icon_size_spin.setValue(int(settings["icon_pixels"]))
            self.tooltip_opacity_spin.setValue(float(settings["opacity"]))
            index = self.tooltip_wording_combo.findData(settings["wording_mode"])
            self.tooltip_wording_combo.setCurrentIndex(max(0, index))
            self.tooltip_icon_size_spin.blockSignals(False)
            self.tooltip_opacity_spin.blockSignals(False)
            self.tooltip_wording_combo.blockSignals(False)
            self._refresh_toolkit_tooltip_preview()

        def _tooltip_wording_mode(self):
            data = self.tooltip_wording_combo.currentData()
            return str(data or "simple")

        def _tooltip_preview_description_text(self):
            mode = self._tooltip_wording_mode()
            if mode == "kid":
                return maya_timing_tools.TOOLKIT_BAR_KID_HELP.get("combine_freeze_pivot")
            if mode == "technical":
                return "Combine selected mesh transforms into one mesh, freeze transforms, then enter Edit Pivot mode."
            return maya_timing_tools.TOOLKIT_BAR_SIMPLE_HELP.get("combine_freeze_pivot")

        def _refresh_toolkit_tooltip_preview(self, *_args):
            if not self.tooltip_preview_card:
                return
            icon_pixels = int(self.tooltip_icon_size_spin.value())
            opacity = float(self.tooltip_opacity_spin.value())
            self.tooltip_preview_icon.setFixedSize(icon_pixels + 6, icon_pixels + 6)
            icon = maya_timing_tools._make_student_core_icon("#55CBCD", "combine_freeze_pivot")
            self.tooltip_preview_icon.setPixmap(icon.pixmap(icon_pixels, icon_pixels))
            self.tooltip_preview_description.setText(self._tooltip_preview_description_text())
            alpha = max(0, min(255, int(round(opacity * 255))))
            self.tooltip_preview_card.setStyleSheet(
                """
                QFrame#aminateCustomizationTooltipPreviewCard {{
                    background-color: rgba(23, 25, 28, {alpha});
                    border: 1px solid #5C5C5C;
                    border-radius: 8px;
                }}
                QLabel#aminateCustomizationTooltipPreviewIcon {{
                    background-color: #24282D;
                    border: 1px solid #3A4148;
                    border-radius: 7px;
                }}
                QLabel#aminateCustomizationTooltipPreviewTitle {{
                    color: #FFFFFF;
                    font-size: 15px;
                    font-weight: 800;
                }}
                QLabel#aminateCustomizationTooltipPreviewDescription {{
                    color: #D7E1E8;
                    font-size: 12px;
                }}
                """.format(alpha=alpha)
            )

        def _apply_toolkit_tooltip_settings(self):
            success, message, _settings = self.controller.set_toolkit_hover_settings(
                icon_pixels=self.tooltip_icon_size_spin.value(),
                opacity=self.tooltip_opacity_spin.value(),
                wording_mode=self._tooltip_wording_mode(),
            )
            self._refresh_toolkit_tooltip_preview()
            self.status_label.setText(message)
            return success

        def _reset_toolkit_tooltip_settings(self):
            success, message, _settings = self.controller.reset_toolkit_hover_settings()
            self._load_toolkit_tooltip_settings()
            self.status_label.setText(message)
            return success

        def _settings_from_ui(self):
            values = {}
            for field in COLOR_FIELDS:
                key = field["key"]
                values[key] = _normalize_hex(self.hex_edits[key].text(), field["default"])
            return values

        def _sync_edit_from_button(self, key, color_hex):
            self.hex_edits[key].setText(_normalize_hex(color_hex, _field_by_key(key)["default"]))
            self._apply_single_color(key)

        def _sync_button_from_edit(self, key):
            color_hex = _normalize_hex(self.hex_edits[key].text(), _field_by_key(key)["default"])
            self.hex_edits[key].setText(color_hex)
            self.color_buttons[key].set_color(color_hex)
            self._apply_single_color(key)

        def _apply_single_color(self, key):
            if key not in self.hex_edits:
                return
            color_hex = _normalize_hex(self.hex_edits[key].text(), _field_by_key(key)["default"])
            success, message, report = self.controller.set_color(key, color_hex, apply_now=True)
            if self.status_label is not None:
                warning_text = "; ".join(report.get("warnings") or [])
                self.status_label.setText("{0}{1}".format(message, (" " + warning_text) if warning_text else ""))
            return success

        def _apply(self):
            for key in list(self.hex_edits.keys()):
                self._sync_button_from_edit(key)
            success, message, report = self.controller.set_settings(self._settings_from_ui(), apply_now=True)
            warning_text = "; ".join(report.get("warnings") or [])
            applied_text = "{0} native slot(s) updated.".format(len(report.get("applied") or []))
            self.status_label.setText("{0} {1}{2}".format(message, applied_text, (" " + warning_text) if warning_text else ""))
            return success

        def _reset(self):
            success, message, report = self.controller.reset_defaults(apply_now=True)
            self._load_settings()
            warning_text = "; ".join(report.get("warnings") or [])
            self.status_label.setText("{0}{1}".format(message, (" " + warning_text) if warning_text else ""))
            return success

        def closeEvent(self, event):
            self.hide()
            event.ignore()


else:
    AminateCustomizationWindow = None


def show_aminate_customization():
    global GLOBAL_WINDOW, GLOBAL_CONTROLLER
    if QtWidgets is None:
        raise RuntimeError("Aminate Customization needs PySide.")
    if GLOBAL_WINDOW is not None:
        try:
            GLOBAL_WINDOW.show()
            GLOBAL_WINDOW.raise_()
            GLOBAL_WINDOW.activateWindow()
            return GLOBAL_WINDOW
        except Exception:
            GLOBAL_WINDOW = None
            GLOBAL_CONTROLLER = None
    parent = _maya_main_window()
    GLOBAL_CONTROLLER = AminateCustomizationController()
    GLOBAL_WINDOW = AminateCustomizationWindow(controller=GLOBAL_CONTROLLER, parent=parent)
    GLOBAL_WINDOW.show()
    return GLOBAL_WINDOW
