"""Build both Parent Manager exercises in a fresh, untitled Maya scene."""

from maya import cmds

from maya_parent_manager import POINT_TAG


GREEN = (0.35, 0.83, 0.48)
BLUE = (0.30, 0.64, 1.0)
ORANGE = (1.0, 0.56, 0.25)
VIOLET = (0.64, 0.51, 0.91)

MATERIAL_COLORS = {
    "BoxGreen": (0.20, 0.62, 0.35),
    "BoxDarkGreen": (0.075, 0.30, 0.16),
    "BoxLightGreen": (0.44, 0.82, 0.52),
    "LeftBlue": (0.14, 0.42, 0.90),
    "LeftBlueGrip": (0.37, 0.69, 1.0),
    "RightOrange": (0.94, 0.43, 0.13),
    "RightOrangeGrip": (1.0, 0.67, 0.32),
    "DarkMetal": (0.20, 0.25, 0.31),
    "TableTop": (0.40, 0.46, 0.54),
    "Floor": (0.24, 0.28, 0.36),
    "Practice_Hand_Violet": VIOLET,
    "Practice_Hand_Fingers": (0.85, 0.76, 1.0),
}


def _materials():
    groups = {}
    for name, color in MATERIAL_COLORS.items():
        shader = cmds.shadingNode("lambert", asShader=True, name=name)
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=name + "SG")
        cmds.setAttr(shader + ".color", *color, type="float3")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        groups[name] = group
    return groups


def _transform(name, parent=None, position=(0, 0, 0), rotation=(0, 0, 0), color=None):
    parent_args = {"parent": parent} if parent else {}
    node = cmds.createNode("transform", name=name, skipSelect=True, **parent_args)
    cmds.setAttr(node + ".translate", *position)
    cmds.setAttr(node + ".rotate", *rotation)
    if color is not None:
        cmds.setAttr(node + ".useOutlinerColor", True)
        cmds.setAttr(node + ".outlinerColor", *color, type="float3")
    return node


def _boxes(parent, groups, parts):
    for name, size, position, material in parts:
        width, height, depth = size
        cube = cmds.polyCube(name=name, width=width, height=height, depth=depth, constructionHistory=False)[0]
        cube = cmds.parent(cube, parent, relative=True)[0]
        cmds.setAttr(cube + ".translate", *position)
        cmds.sets(cube, edit=True, forceElement=groups[material])


def _key_channels(node, frames, **channels):
    for channel, values in channels.items():
        for frame, value in zip(frames, values):
            cmds.setKeyframe(
                node, attribute=channel, time=frame, value=value,
                inTangentType="clamped", outTangentType="clamped",
            )
        cmds.keyTangent(node, attribute=channel, edit=True, weightedTangents=False)


def _handoff_scene(groups):
    box = _transform("Box", position=(-5, 1.65, 0), color=GREEN)
    _boxes(box, groups, (
        ("BoxBody", (2, 1.22, 1.6), (0, 0, 0), "BoxGreen"),
        ("BoxTop", (2.04, 0.08, 1.64), (0, 0.61, 0), "BoxLightGreen"),
    ))
    for side, z in enumerate((-0.824, 0.824)):
        _boxes(box, groups, (
            (f"BoxSlat_{side}_{index}", (1.72, 0.08, 0.045), (0, y, z), "BoxDarkGreen")
            for index, y in enumerate((-0.4, -0.14, 0.12, 0.38))
        ))
    _boxes(box, groups, (
        ("BoxGrip_L", (0.24, 0.16, 0.68), (-1.12, 0, 0), "BoxDarkGreen"),
        ("BoxGrip_R", (0.24, 0.16, 0.68), (1.12, 0, 0), "BoxDarkGreen"),
    ))

    for hand, side, material, color in (
        ("Left_Hand", -1, "LeftBlue", BLUE),
        ("Right_Hand", 1, "RightOrange", ORANGE),
    ):
        control = _transform(hand, color=color)
        _boxes(control, groups, (
            (hand + "_Palm", (0.53, 0.44, 0.63), (side * 0.46, 0, 0), material),
            (hand + "_Wrist", (0.58, 0.28, 0.38), (side * 0.94, 0, 0), "DarkMetal"),
            (hand + "_Finger1", (0.45, 0.21, 0.17), (side * 0.10, 0, -0.37), material + "Grip"),
            (hand + "_Finger2", (0.45, 0.21, 0.17), (side * 0.10, 0, 0.37), material + "Grip"),
        ))
    _key_channels(
        "Left_Hand", (1, 16, 25, 40, 49, 80),
        translateX=(-7.25, -6.25, -4.8, -1.25, -2.85, -3.6),
        translateY=(3, 1.65, 3.65, 3.65, 4.6, 4.6),
        translateZ=(1.3, 0, 0, 0, 1.3, 1.3),
        rotateY=(-12, 0, -14, 0, -18, -18),
    )
    _key_channels(
        "Right_Hand", (1, 27, 40, 52, 64, 72, 80),
        translateX=(4.4, 4.4, 1.25, 4.85, 6.25, 7.05, 7.05),
        translateY=(4.65, 4.65, 3.65, 3.15, 1.65, 2.75, 2.75),
        translateZ=(0.4, 0.4, 0, 0, 0, 1.3, 1.3),
        rotateY=(17, 17, 0, 17, 0, 15, 15),
    )

    stage = _transform("Practice_Stage")
    _boxes(stage, groups, (
        ("Table", (15.8, 0.35, 3.55), (0, 0.787, 0), "TableTop"),
        ("Pickup_Pad", (2.85, 0.04, 2.4), (-5, 0.98, 0), "LeftBlueGrip"),
        ("Setdown_Pad", (2.85, 0.04, 2.4), (5, 0.98, 0), "RightOrangeGrip"),
        ("TableSupport", (0.95, 0.62, 2.55), (-5.7, 0.31, 0), "DarkMetal"),
        ("TableSupport1", (0.95, 0.62, 2.55), (5.7, 0.31, 0), "DarkMetal"),
        ("Ground", (80, 0.08, 80), (0, -0.04, 0), "Floor"),
    ))


def _grip_marker(parent, name, position, rotation, color, label=None):
    node = _transform(name, parent, position, rotation, color=None if label else color)
    shape = cmds.createNode("locator", name=name + "Shape", parent=node, skipSelect=True)
    cmds.setAttr(shape + ".visibility", keyable=False)
    cmds.setAttr(shape + ".localScale", 0.47, 0.47, 0.47)
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color, type="float3")
    if label:
        cmds.addAttr(node, longName=POINT_TAG, dataType="string")
        cmds.setAttr(node + "." + POINT_TAG, label, type="string")
    return node


def _saved_spots_scene(groups, checkpoint):
    lesson = _transform("Lesson_02_Saved_Spots", position=(27, 0, 0))
    stage = _transform("Spots_Stage", parent=lesson)
    _boxes(stage, groups, (
        ("Spots_Workbench", (11, 0.30, 4.1), (0, 0.85, 0), "TableTop"),
        ("Spots_BenchSupport", (0.85, 0.68, 2.9), (-4, 0.34, 0), "DarkMetal"),
        ("Spots_BenchSupport1", (0.85, 0.68, 2.9), (4, 0.34, 0), "DarkMetal"),
    ))

    crate = _transform("Practice_Crate", parent=lesson, color=GREEN)
    _boxes(crate, groups, (
        ("Practice_Crate_Body", (3, 1.78, 2.06), (0, 0, 0), "BoxGreen"),
        ("Practice_Crate_Edge", (3.04, 0.10, 2.11), (0, -0.87, 0), "BoxLightGreen"),
        ("Practice_Crate_Edge1", (3.04, 0.10, 2.11), (0, 0.87, 0), "BoxLightGreen"),
    ))
    _boxes(crate, groups, (
        (f"Practice_Crate_Slat{index or ''}", (2.77, 0.065, 0.026), (0, y, 1.04), "BoxDarkGreen")
        for index, y in enumerate((-0.51, -0.16, 0.19, 0.54))
    ))
    _boxes(crate, groups, (
        ("Blue_Side_Grip", (0.28, 0.28, 0.98), (-1.58, 0, 0), "LeftBlue"),
        ("Blue_Side_Grip_Face", (0.045, 0.20, 0.67), (-1.735, 0, 0), "LeftBlueGrip"),
        ("Orange_Top_Grip", (0.30, 0.24, 0.98), (0.45, 0.99, 0), "RightOrange"),
        ("Orange_Top_Grip_Face", (0.22, 0.045, 0.67), (0.45, 1.13, 0), "RightOrangeGrip"),
    ))
    _key_channels(
        crate, (1, 20, 32, 44, 56, 69, 80),
        translateX=(0.7, 0.7, 1.45, 1.45, 1, 0.25, 0.25),
        rotateY=(0, 0, 13, 13, -8, -18, -18),
    )
    _key_channels(
        crate, (1, 20, 32, 36, 44, 56, 69, 80),
        translateY=(2.04, 2.04, 3.47, 3.47, 2.04, 2.04, 2.75, 2.75),
    )

    _grip_marker(crate, "Blue_Side_Grip_Saved_Spot", (-1.8, 0, 0), (0, 0, 0), BLUE, "Blue side grip")
    top_position, top_rotation = (0.45, 1.18, 0), (0, 0, -90)
    guide = _grip_marker(crate, "Orange_Top_Grip_Guide", top_position, top_rotation, ORANGE)
    if checkpoint:
        cmds.setAttr(guide + ".visibility", False)
        _grip_marker(
            crate, "Orange_Top_Grip_Spot", top_position, top_rotation, (1.0, 0.66, 0.24), "Orange top grip",
        )

    hand = _transform("Practice_Hand", lesson, (-3.6, 3.7, 0.38), (0, 14, 18), VIOLET)
    _boxes(hand, groups, (
        ("Practice_Hand_Palm", (0.64, 0.44, 0.68), (-0.55, 0, 0), "Practice_Hand_Violet"),
        ("Practice_Hand_Wrist", (0.53, 0.30, 0.38), (-1.07, 0, 0), "DarkMetal"),
        ("Practice_Hand_Finger", (0.64, 0.22, 0.19), (-0.095, 0, -0.42), "Practice_Hand_Fingers"),
        ("Practice_Hand_Finger1", (0.64, 0.22, 0.19), (-0.095, 0, 0.42), "Practice_Hand_Fingers"),
    ))

    camera = _transform(
        "Saved_Spots_Camera", lesson, (-2.4, 7, 13.7), (-18.3510219717, -8.9189286180, 0),
    )
    shape = cmds.createNode("camera", name="Saved_Spots_CameraShape", parent=camera, skipSelect=True)
    cmds.setAttr(shape + ".visibility", keyable=False)
    cmds.setAttr(shape + ".renderable", False)
    cmds.setAttr(shape + ".focalLength", 37)
    cmds.setAttr(shape + ".centerOfInterest", 14.6)
    for attribute, suffix in (("imageName", ""), ("depthName", "_depth"), ("maskName", "_mask")):
        cmds.setAttr(shape + "." + attribute, "Saved_Spots_Camera" + suffix, type="string")


def build_practice_scene(lesson):
    """Populate the caller's empty scene with the handoff or saved-grips checkpoint."""
    if lesson not in ("handoff", "attach_points"):
        raise ValueError(f"Unknown Parent Manager practice lesson: {lesson!r}")

    checkpoint = lesson == "attach_points"
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    groups = _materials()
    _handoff_scene(groups)
    _saved_spots_scene(groups, checkpoint)

    cmds.setAttr("|persp.translate", 3.1, 8.3, 23)
    cmds.setAttr("|persp.rotate", -15.1874309729, 7.6762147536, 0)
    cmds.setAttr("|persp|perspShape.focalLength", 39)
    cmds.setAttr("|persp|perspShape.centerOfInterest", 24)
    for camera in ("top", "front", "side"):
        cmds.setAttr(f"|{camera}|{camera}Shape.orthographicWidth", 30)

    cmds.playbackOptions(minTime=1, maxTime=80, animationStartTime=1, animationEndTime=80)
    cmds.currentTime(9 if checkpoint else 1)
    cmds.select(clear=True)
