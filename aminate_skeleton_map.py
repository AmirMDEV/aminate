"""Host-independent skeleton descriptions, mapping suggestions and validation.

Suggestions are evidence, not anatomical truth. User locks win; ambiguous names
remain reviewable. Limb groups have arbitrary ids so creatures can have more
than one pair of arms.
"""
from __future__ import absolute_import, division, print_function
import json
import math
import re

VERSION = 1
ALIASES = {
    "root": ("root", "rootmotion", "reference", "master"),
    "pelvis": ("pelvis", "hips", "hip"), "spine": ("spine", "abdomen", "waist"),
    "chest": ("chest", "thorax", "upperchest"), "neck": ("neck",), "head": ("head", "skull"),
    "clavicle": ("clavicle", "clav", "collar", "shoulder"),
    "upperarm": ("upperarm", "uparm", "arm", "humerus"),
    "forearm": ("forearm", "lowerarm", "loarm", "elbow"), "hand": ("hand", "wrist"),
    "thigh": ("thigh", "upleg", "upperleg", "femur"),
    "shin": ("shin", "calf", "lowerleg", "leg", "knee"), "foot": ("foot", "ankle"),
    "toe": ("toe", "toebase", "ball"),
}
HELPERS = {"twist", "roll", "end", "nub", "socket", "ik", "pole", "effector"}
IGNORE = {"def", "j", "skel", "jnt", "joint", "bone", "bip", "bip01", "mixamorig", "rig"}
SIDE = {"l": "left", "lf": "left", "left": "left", "r": "right", "rt": "right", "right": "right"}
ROLE_ORDER = ["root", "pelvis", "spine", "chest", "neck", "head"] + [s + "." + r for s in ("left", "right") for r in ("clavicle", "upperarm", "forearm", "hand", "thigh", "shin", "foot", "toe")]
ROLE_PARENT = {"pelvis":"root", "spine": "pelvis", "chest": "spine", "neck": "chest", "head": "neck"}
for _side in ("left", "right"):
    ROLE_PARENT[_side+".clavicle"]="chest"
    ROLE_PARENT[_side+".upperarm"]=_side+".clavicle"
    ROLE_PARENT[_side+".thigh"]="pelvis"
    for _child, _parent in (("forearm", "upperarm"), ("hand", "forearm"), ("shin", "thigh"), ("foot", "shin"), ("toe", "foot")):
        ROLE_PARENT[_side + "." + _child] = _side + "." + _parent


def tokens(name):
    name = name.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return re.findall(r"[a-z]+|\d+", name.lower())


def name_evidence(name, aliases=None):
    parts = tokens(name)
    side = next((SIDE[p] for p in parts if p in SIDE), None)
    core = [p for p in parts if p not in IGNORE and p not in SIDE and not p.isdigit()]
    text = "".join(core)
    rules = dict(ALIASES)
    for key, values in (aliases or {}).items():
        rules[key] = tuple(rules.get(key, ())) + tuple(values)
    roles = [role for role, names in rules.items() if text in names or any(x in core for x in names)]
    # Compound anatomical terms outrank their broad final token (upper arm).
    exact = [role for role, names in rules.items() if text in names]
    compounds=[role for role,names in rules.items() if any("".join(core[i:i+2]) in names for i in range(len(core)-1))]
    return {"side": side, "roles": exact or compounds or roles, "helper": bool(set(parts) & HELPERS), "tokens": parts}


def path_between(nodes, ancestor, descendant):
    path, seen = [], set()
    while descendant:
        if descendant in seen or descendant not in nodes:
            return []
        seen.add(descendant)
        path.append(descendant)
        if descendant == ancestor:
            return list(reversed(path))
        descendant = nodes[descendant].get("parent")
    return []


def validate_description(description):
    nodes = description.get("nodes", {})
    if not nodes:
        raise ValueError("Choose a skeleton containing joints.")
    for key, node in nodes.items():
        position = node.get("position", [])
        if len(position) != 3 or not all(math.isfinite(float(x)) for x in position):
            raise ValueError("Invalid joint position: " + key)
        seen, current = set(), key
        while current in nodes:
            if current in seen:
                raise ValueError("Skeleton hierarchy contains a cycle.")
            seen.add(current)
            current = nodes[current].get("parent")
    return nodes


def suggest(description, locked=None, aliases=None):
    """Constrained beam assignment with name, side and hierarchy evidence.

Spatial side hints require a user-confirmed character-left vector. Geometry
alone never earns a strong anatomical assignment.
"""
    nodes = validate_description(description)
    locked = dict(locked or {})
    if any(n not in nodes for n in locked.values()) or len(set(locked.values())) != len(locked):
        raise ValueError("Locked slots must reference distinct joints in this skeleton.")
    if set(locked)-set(ROLE_ORDER):raise ValueError("Unknown anatomical slots in the locked map.")
    for role,ident in locked.items():
        parent_role=ROLE_PARENT.get(role)
        while parent_role:
            if parent_role in locked and not path_between(nodes,locked[parent_role],ident):
                raise ValueError("Confirmed roles conflict with the skeleton hierarchy: "+parent_role+" / "+role)
            parent_role=ROLE_PARENT.get(parent_role)
    evidence = {n: name_evidence(v["name"], aliases) for n, v in nodes.items()}
    candidates = {}
    origin = description.get("origin", [0, 0, 0])
    left = description.get("left_axis")
    for role in ROLE_ORDER:
        side, _, part = role.rpartition(".")
        part = part or role
        ranked = []
        for node_id, node in nodes.items():
            e = evidence[node_id]
            if e["helper"] or part not in e["roles"]:
                continue
            score, why = 4., ["anatomical name"]
            if side and e["side"]:
                if side != e["side"]:
                    continue
                score += 3; why.append("side label")
            elif side and left:
                dot = sum((p-o)*a for p, o, a in zip(node["position"], origin, left))
                if abs(dot) > 1e-5:
                    if (dot > 0) != (side == "left"):
                        continue
                    score += 1; why.append("confirmed character side")
            elif side:
                score -= 1; why.append("side needs checking")
            if not side and e["side"]:
                continue
            ranked.append((score, node_id, why))
        candidates[role] = sorted(ranked, key=lambda x: (-x[0], x[1]))[:6]
    # Common game skeletons name every torso joint Spine_01/02/03. The
    # terminal spine before a named neck is an anatomical chest suggestion.
    if not candidates["chest"]:
        for _score,spine_id,_why in candidates["spine"]:
            for _neck_score,neck_id,_neck_why in candidates["neck"]:
                if not path_between(nodes,spine_id,neck_id):continue
                deeper=[n for _,n,_ in candidates["spine"] if n!=spine_id and path_between(nodes,spine_id,n) and path_between(nodes,n,neck_id)]
                if not deeper:candidates["chest"].append((3.5,spine_id,["terminal spine before neck","review chest placement"]))
    # Manual endpoint anchors allow unnamed or unfamiliar skeletons to be
    # completed from topology. Keep these suggestions explicitly reviewable.
    anchor_chains=[("pelvis","spine","chest","neck","head")]
    for side in ("left","right"):
        anchor_chains.extend(tuple(side+"."+p for p in chain) for chain in (("upperarm","forearm","hand"),("thigh","shin","foot","toe")))
    for roles in anchor_chains:
        anchors=[(i,locked[r]) for i,r in enumerate(roles) if r in locked]
        for (a,start),(b,end) in zip(anchors,anchors[1:]):
            path=path_between(nodes,start,end)
            interior=[n for n in path[1:-1] if not evidence[n]["helper"]]
            if not interior:continue
            distances=[0.]
            for first,second in zip(path,path[1:]):distances.append(distances[-1]+math.dist(nodes[first]["position"],nodes[second]["position"]))
            total=distances[-1]
            for index in range(a+1,b):
                role=roles[index]
                for ident in interior:
                    fraction=distances[path.index(ident)]/total if total>1e-8 else path.index(ident)/max(1,len(path)-1)
                    score=3.-abs(fraction-(index-a)/(b-a))
                    if ident not in [x[1] for x in candidates[role]]:candidates[role].append((score,ident,["hierarchy between confirmed anchors","proportional chain position"]))
                candidates[role]=sorted(candidates[role],key=lambda x:(-x[0],x[1]))[:6]
    beam = [(0., {}, set())]
    for role in ROLE_ORDER:
        options = [(20., locked[role], ["user assignment"])] if role in locked else candidates[role] + [(0., None, [])]
        expanded = []
        for score, mapping, used in beam:
            for points, node_id, why in options:
                if node_id in used:
                    continue
                parent_role=ROLE_PARENT.get(role)
                while parent_role and parent_role not in mapping:parent_role=ROLE_PARENT.get(parent_role)
                parent = mapping.get(parent_role)
                if node_id and parent and not path_between(nodes, parent, node_id):
                    continue
                extra = 2. if node_id and parent else 0.
                new = dict(mapping)
                if node_id:
                    new[role] = node_id
                expanded.append((score + points + extra, new, used | ({node_id} if node_id else set())))
        if not expanded:
            raise ValueError("The locked map conflicts with the hierarchy near " + role)
        beam = sorted(expanded, key=lambda x: -x[0])[:64]
    mapping = beam[0][1]
    result = {}
    for role in ROLE_ORDER:
        node_id = mapping.get(role)
        ranked = candidates[role]
        selected = next((x for x in ranked if x[1] == node_id), None)
        margin = (selected[0] - max([x[0] for x in ranked if x[1] != node_id] or [0])) if selected else 0
        strong = bool(selected and "anatomical name" in selected[2] and margin >= 2 and ("." not in role or evidence[node_id]["side"]))
        result[role] = {"node": node_id, "status": "Confirmed" if role in locked else "Strong match" if strong else "Check" if node_id else "Missing",
                        "why": ["user assignment"] if role in locked else selected[2] if selected else ["no consistent candidate"],
                        "candidates": [x[1] for x in ranked]}
    return result


def humanoid_modules(mapping, description):
    nodes = validate_description(description)
    result = []
    for side in ("left", "right"):
        for kind, parts in (("arm", ("upperarm", "forearm", "hand")), ("leg", ("thigh", "shin", "foot"))):
            chain = [mapping.get(side + "." + p) for p in parts]
            if all(chain):
                result.append({"id": side + "_" + kind, "kind": kind, "joints": chain, "ik": True})
    validate_modules(result, nodes)
    return result


def validate_modules(modules, nodes):
    ids, primary = set(), set()
    for module in modules:
        ident, chain = module.get("id", ""), module.get("joints", [])
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", ident) or ident in ids:
            raise ValueError("Limb group ids must be unique names using letters, digits and underscores.")
        ids.add(ident)
        if len(chain) != 3 or len(set(chain)) != 3 or any(j not in nodes for j in chain):
            raise ValueError(ident + " needs three distinct joints: start, middle and end.")
        if primary.intersection(chain):
            raise ValueError("Two limb groups cannot drive the same primary joints.")
        primary.update(chain)
        if not path_between(nodes, chain[0], chain[1]) or not path_between(nodes, chain[1], chain[2]):
            raise ValueError(ident + " is not a connected ordered limb.")
    return True


def save_profile(path, description, mapping, modules, aliases=None):
    nodes = validate_description(description)
    # Relative paths disambiguate duplicate short names. UUIDs are only valid
    # in the current scene and are never used as portable preset identities.
    names = {n: nodes[n]["path"] for n in nodes}
    data = {"version": VERSION, "mapping": {r: names[n] for r, n in mapping.items()},
            "modules": [dict(m, joints=[names[n] for n in m["joints"]]) for m in modules], "aliases": aliases or {}}
    with open(path, "w") as stream:
        json.dump(data, stream, indent=2)


def load_profile(path, description):
    with open(path) as stream:
        data = json.load(stream)
    if data.get("version") != VERSION:
        raise ValueError("Unsupported mapping profile version.")
    by_path = {}
    for key, node in validate_description(description).items():
        by_path.setdefault(node["path"], []).append(key)
    def resolve(path):
        matches = by_path.get(path, [])
        if len(matches) != 1:
            raise ValueError("Preset path is missing or ambiguous: " + path)
        return matches[0]
    mapping = {r: resolve(p) for r, p in data["mapping"].items()}
    modules = [dict(m, joints=[resolve(p) for p in m["joints"]]) for m in data["modules"]]
    validate_modules(modules, description["nodes"])
    return mapping, modules, data.get("aliases", {})


def route_time(frame, route, fps):
    speed = float(route.get("speed", 1.))
    if speed <= 0 or not math.isfinite(speed) or fps <= 0:
        raise ValueError("Playback speed and scene FPS must be positive.")
    value = float(route["source_start"]) + (float(frame)-float(route["target_start"]))*speed + float(route.get("offset_seconds", 0))*fps
    if not math.isfinite(value):
        raise ValueError("Invalid clip timing.")
    return value


def validate_routes(routes):
    claimed = set()
    for route in routes:
        targets = route.get("targets", [])
        sources = route.get("sources", [])
        if not targets or len(targets) != len(sources) or len(set(targets)) != len(targets):
            raise ValueError("Every route needs equal source/target counts and distinct target controls.")
        if claimed.intersection(targets):
            raise ValueError("Two performers cannot own the same target control. Split their limb groups.")
        claimed.update(targets)
        route_time(route.get("target_start", 0), route, 24.)
        if "source_end" in route:
            end=float(route["source_end"])
            if not math.isfinite(end) or end<float(route["source_start"]):raise ValueError("Source clip bounds must be finite and ordered.")
        weight = float(route.get("weight", 1.))
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("Route weight must be between zero and one.")
    if not routes:
        raise ValueError("Add a performer route first.")
    return True
