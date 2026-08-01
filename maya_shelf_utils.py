"""
maya_shelf_utils.py

Shared Maya shelf installation helpers for shelf-installable tools.
"""

from __future__ import absolute_import, division, print_function

import os

try:
    import maya.cmds as cmds
    import maya.mel as mel

    MAYA_AVAILABLE = True
except Exception:
    cmds = None
    mel = None
    MAYA_AVAILABLE = False


DEFAULT_SHELF_NAME = "Amir's Scripts"
DEFAULT_SHELF_ICON = "commandButton.png"
DEFAULT_SHELF_STYLE = "iconAndTextVertical"
DEFAULT_SHELF_SOURCE_TYPE = "python"


def ensure_maya_available():
    if not (MAYA_AVAILABLE and cmds and mel):
        raise RuntimeError("Shelf installation must run inside Autodesk Maya.")


def shelf_top_level():
    ensure_maya_available()
    shelf_top = mel.eval("$tmpVar=$gShelfTopLevel")
    if not shelf_top:
        raise RuntimeError("Could not resolve Maya's top-level shelf layout.")
    return shelf_top


def sanitize_shelf_name(shelf_name):
    sanitized = []
    for character in shelf_name:
        if character.isalnum() or character == "_":
            sanitized.append(character)
        else:
            sanitized.append("_")
    return "".join(sanitized).strip("_") or "CustomShelf"


def resolve_shelf_layout(shelf_top, shelf_name):
    ensure_maya_available()
    internal_name = sanitize_shelf_name(shelf_name)
    child_names = cmds.shelfTabLayout(shelf_top, query=True, childArray=True) or []
    tab_labels = cmds.shelfTabLayout(shelf_top, query=True, tabLabel=True) or []
    for index, child_name in enumerate(child_names):
        visible_label = tab_labels[index] if index < len(tab_labels) else child_name
        if visible_label in (shelf_name, internal_name) or child_name in (shelf_name, internal_name):
            if visible_label != shelf_name:
                try:
                    cmds.shelfTabLayout(
                        shelf_top,
                        edit=True,
                        tabLabel=(child_name, shelf_name),
                    )
                except Exception:
                    pass
            return child_name

    if cmds.shelfLayout(internal_name, exists=True):
        try:
            cmds.shelfTabLayout(
                shelf_top,
                edit=True,
                tabLabel=(internal_name, shelf_name),
            )
        except Exception:
            pass
        return internal_name

    shelf_layout = cmds.shelfLayout(internal_name, parent=shelf_top)
    cmds.shelfTabLayout(shelf_top, edit=True, tabLabel=(shelf_layout, shelf_name))
    return shelf_layout


def remove_buttons_by_doc_tag(shelf_layout, doc_tag):
    ensure_maya_available()
    existing_buttons = cmds.shelfLayout(shelf_layout, query=True, childArray=True) or []
    for child in existing_buttons:
        if not cmds.control(child, exists=True):
            continue
        try:
            existing_doc_tag = cmds.shelfButton(child, query=True, docTag=True)
        except Exception:
            existing_doc_tag = ""
        if existing_doc_tag != doc_tag:
            continue
        try:
            cmds.deleteUI(child)
        except Exception:
            pass


def save_shelf(shelf_top, shelf_layout):
    ensure_maya_available()
    shelf_file_path = None
    try:
        shelf_dir = cmds.internalVar(userShelfDir=True)
        shelf_file_path = os.path.join(shelf_dir, "shelf_{0}.mel".format(shelf_layout))
        duplicate_shelf_path = shelf_file_path + ".mel"
        cmds.saveAllShelves(shelf_top)
        if os.path.exists(duplicate_shelf_path):
            try:
                os.remove(duplicate_shelf_path)
            except Exception:
                pass
    except Exception:
        pass
    return shelf_file_path


def install_shelf_button(
    command_text,
    doc_tag,
    annotation,
    button_label,
    image_overlay_label,
    shelf_name=DEFAULT_SHELF_NAME,
    image=DEFAULT_SHELF_ICON,
    style=DEFAULT_SHELF_STYLE,
    width=None,
    height=None,
    source_type=DEFAULT_SHELF_SOURCE_TYPE,
):
    ensure_maya_available()
    shelf_top = shelf_top_level()
    shelf_layout = resolve_shelf_layout(shelf_top, shelf_name)
    remove_buttons_by_doc_tag(shelf_layout, doc_tag)
    button_kwargs = {
        "parent": shelf_layout,
        "label": button_label,
        "annotation": annotation,
        "image": image,
        "imageOverlayLabel": image_overlay_label,
        "style": style,
        "sourceType": source_type,
        "command": command_text,
        "docTag": doc_tag,
    }
    if width is not None:
        button_kwargs["width"] = int(width)
    if height is not None:
        button_kwargs["height"] = int(height)
    button = cmds.shelfButton(
        **button_kwargs
    )
    cmds.shelfTabLayout(shelf_top, edit=True, selectTab=shelf_layout)
    shelf_file_path = save_shelf(shelf_top, shelf_layout)
    return {
        "button": button,
        "shelf_layout": shelf_layout,
        "shelf_top_level": shelf_top,
        "shelf_file_path": shelf_file_path,
    }


__all__ = [
    "DEFAULT_SHELF_NAME",
    "ensure_maya_available",
    "install_shelf_button",
    "remove_buttons_by_doc_tag",
    "resolve_shelf_layout",
    "sanitize_shelf_name",
    "save_shelf",
    "shelf_top_level",
]
