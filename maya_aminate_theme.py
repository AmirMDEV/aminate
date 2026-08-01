"""Small, Maya-local theme registry for Aminate's workbench themes.

Both choices are neutral DCC themes.  Neither paints every tool with its icon
colour or uses accent borders.  Old saved theme names remain accepted so an
upgrade never strands a user's optionVar.
"""

from __future__ import absolute_import, division, print_function

import re

import maya_aminate_icon_manifest

try:
    import maya.cmds as cmds
except Exception:
    cmds = None


THEME_OPTION_VAR = "AminateTheme"
DEFAULT_THEME_NAME = "Maya Graphite"
SPECTRUM_THEME_NAME = "Studio Contrast"
THEME_NAMES = (DEFAULT_THEME_NAME, SPECTRUM_THEME_NAME)
LEGACY_THEME_ALIASES = {
    "Material Dark": DEFAULT_THEME_NAME,
    "Toolkit Spectrum": SPECTRUM_THEME_NAME,
}

# The main Aminate tabs intentionally use these longer teaching labels while
# the icon manifest keeps shorter product names. Keep the bridge explicit so
# every visible tab receives its owned toolbar accent.
TAB_LABEL_ALIASES = {
    "Animators Pencil": "animators_pencil",
    "Controls Retargeter (Face and Body)": "controls_retargeter",
}

_MEMORY_THEME_NAME = DEFAULT_THEME_NAME
_THEME_CHANGED_CALLBACKS = []


def _normalise_theme_name(value):
    text = str(value or "").strip()
    text = LEGACY_THEME_ALIASES.get(text, text)
    return text if text in THEME_NAMES else DEFAULT_THEME_NAME


def available_themes():
    """Return stable descriptors used by the Customization dropdown."""
    return (
        {
            "name": DEFAULT_THEME_NAME,
            "description": "Compact graphite surfaces tuned to Maya's native chrome.",
            "preview": "Neutral controls with one restrained slate primary action.",
        },
        {
            "name": SPECTRUM_THEME_NAME,
            "description": "A deeper neutral workbench for brighter or high-glare displays.",
            "preview": "Higher surface contrast without per-tool colours or accent borders.",
        },
    )


def accent_map():
    """Return ``tool_id -> accent`` directly from the icon manifest."""
    return dict(
        (str(entry["id"]), str(entry["accent"]).upper())
        for entry in maya_aminate_icon_manifest.WORKFLOW_ICON_MANIFEST
        if entry.get("id") and entry.get("accent")
    )


def tab_id_map():
    """Return the stable manifest tab id to display-name mapping."""
    return dict(
        (str(entry["tab"]), str(entry["display_name"]))
        for entry in maya_aminate_icon_manifest.WORKFLOW_ICON_MANIFEST
    )


def tool_id_for_tab(tab_name):
    """Resolve a visible Aminate tab label to its manifest tool id."""
    label = str(tab_name or "").strip()
    alias = TAB_LABEL_ALIASES.get(label)
    if alias:
        return alias
    for entry in maya_aminate_icon_manifest.WORKFLOW_ICON_MANIFEST:
        if label in (str(entry.get("display_name") or ""), str(entry.get("tab") or "")):
            return str(entry["id"])
    return ""


def load_theme_name():
    global _MEMORY_THEME_NAME
    if cmds is not None:
        try:
            if cmds.optionVar(exists=THEME_OPTION_VAR):
                return _normalise_theme_name(cmds.optionVar(query=THEME_OPTION_VAR))
        except Exception:
            pass
    return _normalise_theme_name(_MEMORY_THEME_NAME)


def get_theme_name():
    """Public alias for callers that prefer a get/set registry API."""
    return load_theme_name()


def save_theme_name(theme_name):
    global _MEMORY_THEME_NAME
    canonical = _normalise_theme_name(theme_name)
    _MEMORY_THEME_NAME = canonical
    if cmds is not None:
        try:
            cmds.optionVar(stringValue=(THEME_OPTION_VAR, canonical))
        except Exception:
            pass
    return canonical


def register_theme_changed_callback(callback):
    """Register a lightweight callback and return an unregister function."""
    if callable(callback) and callback not in _THEME_CHANGED_CALLBACKS:
        _THEME_CHANGED_CALLBACKS.append(callback)

    def unregister():
        try:
            _THEME_CHANGED_CALLBACKS.remove(callback)
        except ValueError:
            pass

    return unregister


def set_theme_name(theme_name, notify=True):
    canonical = save_theme_name(theme_name)
    if notify:
        for callback in tuple(_THEME_CHANGED_CALLBACKS):
            try:
                callback(canonical)
            except Exception:
                pass
    return canonical


def set_theme(theme_name, notify=True):
    """Public alias for callers that prefer a concise registry API."""
    return set_theme_name(theme_name, notify=notify)


def _root_selector(root_object_name):
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "", str(root_object_name or "aminateWindow"))
    return "#{0}[aminateTheme=\"{1}\"]".format(safe_name, SPECTRUM_THEME_NAME)


def render_spectrum_stylesheet(root_object_name="aminateWindow"):
    """Render the root-scoped, accent-free Studio Contrast option."""
    root = _root_selector(root_object_name)
    lines = [
        "/* AMINATE_THEME_BEGIN Studio Contrast */",
        "{0} {{ background-color: #2E3033; color: #F4F4F4; }}".format(root),
        "{0} QWidget[aminateTabPage=\"true\"] {{ background-color: #2E3033; color: #F4F4F4; }}".format(root),
        "{0} QTabWidget#aminateTabWidget::pane {{ background-color: #2E3033; border: 0px; }}".format(root),
        "{0} QWidget#aminateToolNavigation {{ background-color: #3A3D41; border: 0px; }}".format(root),
        "{0} QComboBox#aminateToolPicker {{ background-color: #4A4E53; border-color: #62676D; color: #FFFFFF; }}".format(root),
        "{0} QComboBox#aminateToolPicker::drop-down {{ width: 22px; border-left: 1px solid #62676D; background-color: #42464A; }}".format(root),
        "{0} QComboBox#aminateToolPicker::drop-down:hover {{ background-color: #555A60; }}".format(root),
        "{0} QFrame#aminateTabIntro {{ background-color: transparent; border: 0px; }}".format(root),
        "{0} QWidget#aminateIntroHelp {{ background-color: #3A3D41; border: 0px; }}".format(root),
        "{0} QGroupBox {{ background-color: transparent; border: 0px; }}".format(root),
        "{0} QPushButton {{ background-color: #4A4E53; border-color: #5D6268; }}".format(root),
        "{0} QPushButton:hover {{ background-color: #555A60; border-color: #686E75; }}".format(root),
        "{0} QPushButton[aminateRole=\"primary\"] {{ background-color: #556979; color: #FFFFFF; border-color: #556979; }}".format(root),
        "{0} QPushButton[aminateRole=\"primary\"]:hover, {0} QPushButton[aminateRole=\"primary\"]:focus {{ background-color: #647C8E; border-color: #647C8E; }}".format(root),
        "{0} QListWidget::item:selected, {0} QTreeWidget::item:selected, {0} QTableWidget::item:selected {{ background-color: #66717D; color: #FFFFFF; }}".format(root),
        "{0} QToolButton#aminateIntroToggle {{ background-color: transparent; border: 0px; }}".format(root),
        "{0} QToolButton#aminateIntroToggle:hover {{ background-color: #4A4E53; }}".format(root),
    ]
    lines.append("/* AMINATE_THEME_END */")
    return "\n".join(lines) + "\n"


def apply_theme_to_window(window, theme_name=None, active_tool_id=None, active_accent=None):
    """Apply a theme to an Aminate root and repolish immediately."""
    if window is None:
        return DEFAULT_THEME_NAME
    canonical = _normalise_theme_name(theme_name or load_theme_name())
    try:
        previous_theme = window.property("aminateTheme")
        window.setProperty("aminateTheme", canonical)
        if active_tool_id:
            window.setProperty("aminateActiveTool", str(active_tool_id))
        if active_accent:
            window.setProperty("aminateActiveAccent", str(active_accent).upper())
        current = str(window.styleSheet() or "")
        spectrum_present = "/* AMINATE_THEME_BEGIN Studio Contrast */" in current
        if previous_theme == canonical and ((canonical == SPECTRUM_THEME_NAME and spectrum_present) or (canonical == DEFAULT_THEME_NAME and not spectrum_present)):
            # Active-tool changes only alter dynamic properties.  Do not
            # rebuild the large stylesheet on every tab click.
            _repolish_theme_targets(window)
            return canonical
        current = re.sub(r"/\* AMINATE_THEME_BEGIN.*?/\* AMINATE_THEME_END \*/\s*", "", current, flags=re.DOTALL)
        if canonical == SPECTRUM_THEME_NAME:
            current = current.rstrip() + "\n" + render_spectrum_stylesheet(window.objectName())
        window.setStyleSheet(current)
        _repolish_theme_targets(window)
    except Exception:
        pass
    return canonical


def _repolish_theme_targets(window):
    """Repolish the root and dynamic-property hosts after an accent change."""
    try:
        style = window.style()
    except Exception:
        style = None
    if style is None:
        return
    targets = [window]
    for attribute_name in ("tool_navigation_widget", "tab_widget"):
        target = getattr(window, attribute_name, None)
        if target is not None:
            targets.append(target)
            try:
                if attribute_name == "tab_widget":
                    targets.append(target.tabBar())
                    targets.append(target.currentWidget())
            except Exception:
                pass
    seen = set()
    for target in targets:
        if target is None or id(target) in seen:
            continue
        seen.add(id(target))
        try:
            style.unpolish(target)
            style.polish(target)
            target.update()
        except Exception:
            pass


def bind_theme_selector(parent_layout, parent_widget=None, on_changed=None):
    """Build the stable theme dropdown for a retained customization panel.

    This compatibility helper is optional; the integrated Customization window
    uses the same object names and registry directly.  It lets an older loaded
    panel bind the new selector without reloading Maya modules.
    """
    try:
        try:
            from PySide6 import QtWidgets
        except Exception:
            from PySide2 import QtWidgets
    except Exception:
        return None
    if parent_layout is None:
        return None
    group = QtWidgets.QGroupBox("Aminate Theme", parent_widget)
    group.setObjectName("aminateCustomizationThemeGroup")
    layout = QtWidgets.QVBoxLayout(group)
    row = QtWidgets.QHBoxLayout()
    row.addWidget(QtWidgets.QLabel("Theme"))
    combo = QtWidgets.QComboBox(group)
    combo.setObjectName("aminateCustomizationThemeCombo")
    combo.setToolTip("Choose the Aminate workbench contrast treatment.")
    for descriptor in available_themes():
        combo.addItem(descriptor["name"], descriptor["name"])
    row.addWidget(combo, 1)
    layout.addLayout(row)
    helper = QtWidgets.QLabel(
        "Both themes stay neutral and compact. Studio Contrast raises surface separation without per-tool colours."
    )
    helper.setWordWrap(True)
    helper.setObjectName("aminateCustomizationThemeHelper")
    layout.addWidget(helper)
    parent_layout.addWidget(group)

    def changed(_index):
        name = set_theme_name(combo.currentData())
        root = parent_widget or group
        while root is not None:
            try:
                if root.objectName() == "aminateWindow":
                    apply_theme_to_window(root, name)
                    break
                root = root.parentWidget()
            except Exception:
                break
        if callable(on_changed):
            on_changed(name)

    combo.currentIndexChanged.connect(changed)
    combo.setCurrentIndex(max(0, combo.findData(load_theme_name())))
    return combo
