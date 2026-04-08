from collections import defaultdict
import os
import math

import ifcopenshell
import ifcopenshell.geom

import numpy as np


# =================================================
# CONFIG (adjustable per project)
# =================================================

CONFIG = {
    # Earthwork: Excavation slope/work surface coefficients (for foundation types)
    "earthwork": {
        "excavation_factor": 1.20,   # Excavation volume = Foundation "enclosing approx volume" * factor
        "backfill_factor": 1.00,     # Backfill volume = (Excavation - Concrete) * factor
        "apply_to_types": {"IfcFooting", "IfcPile"}  # Which components participate in earthwork
    },

    # Rebar content empirical values (kg/m3) - used as fallback estimation when IFC has no detailed rebar
    "rebar_ratio_kg_per_m3": {
        "IfcFooting": 120,
        "IfcColumn": 160,
        "IfcColumnType": 160,
        "IfcBeam": 140,
        "IfcWallStandardCase": 110,
        "IfcSlab": 90,
        "IfcRoof": 60,
        "IfcRampFlight": 100,
        "IfcStairFlight": 110,
        "IfcPile": 120,
    },

    # Formwork: Rough estimation using surface area * coefficient (commonly based on side form/contant area in engineering, adjustable per project)
    "formwork": {
        "factor_default": 0.70,
        "factor_by_type": {
            "IfcSlab": 0.45,             # Slab formwork typically based on bottom form
            "IfcWallStandardCase": 0.80, # Wall side form has higher proportion
            "IfcFooting": 0.65,
            "IfcBeam": 0.75,
            "IfcColumn": 0.80,
        }
    },

    # Opening deductions: Default deduction by area (m2)
    "openings": {
        "deduct_by": "area",   # area or volume
        "unit": "m2",
    },

    # BOQ codes/divisions/items/measurement units/main measurement fields
    # You can replace codes according to local BOQ coding system
    "boq_map": [
        # Earthwork
        ("IfcFooting",          "01.01.01", "Foundation Engineering", "Earth Excavation",       "m3", "earth_exc"),
        ("IfcFooting",          "01.01.02", "Foundation Engineering", "Earth Backfill",       "m3", "earth_bf"),

        # Foundation
        ("IfcFooting",          "01.02.01", "Foundation Engineering", "Independent Foundation Concrete", "m3", "volume"),
        ("IfcFooting",          "01.02.02", "Foundation Engineering", "Independent Foundation Formwork",   "m2", "formwork"),
        ("IfcFooting",          "01.02.03", "Foundation Engineering", "Independent Foundation Rebar",   "t",  "rebar"),

        # Column
        ("IfcColumn",           "01.03.01", "Main Structure", "Concrete Column",       "m3", "volume"),
        ("IfcColumn",           "01.03.02", "Main Structure", "Column Formwork",         "m2", "formwork"),
        ("IfcColumn",           "01.03.03", "Main Structure", "Column Rebar",         "t",  "rebar"),

        ("IfcColumnType::",     "01.03.10", "Main Structure", "Column (by type) Concrete/Steel", "-", "composite_column"),

        # Beam
        ("IfcBeam",             "01.04.01", "Main Structure", "Beam Concrete (if applicable)", "m3", "volume"),
        ("IfcBeam",             "01.04.02", "Main Structure", "Beam Formwork",         "m2", "formwork"),
        ("IfcBeam",             "01.04.03", "Main Structure", "Beam Rebar",         "t",  "rebar"),
        ("IfcBeam",             "01.04.04", "Main Structure", "Beam (by length)",   "m",  "length"),

        # Slab
        ("IfcSlab",             "01.05.01", "Main Structure", "Floor Slab (by area)", "m2", "area"),
        ("IfcSlab",             "01.05.02", "Main Structure", "Slab Concrete (reference)", "m3", "volume"),
        ("IfcSlab",             "01.05.03", "Main Structure", "Slab Formwork",       "m2", "formwork"),
        ("IfcSlab",             "01.05.04", "Main Structure", "Slab Rebar",       "t",  "rebar"),

        # Wall
        ("IfcWallStandardCase", "01.06.01", "Enclosure Structure", "Wall (by area)", "m2", "area"),
        ("IfcWallStandardCase", "01.06.02", "Enclosure Structure", "Wall Concrete (reference)", "m3", "volume"),
        ("IfcWallStandardCase", "01.06.03", "Enclosure Structure", "Wall Formwork",       "m2", "formwork"),
        ("IfcWallStandardCase", "01.06.04", "Enclosure Structure", "Wall Rebar",       "t",  "rebar"),

        # Roof
        ("IfcRoof",             "01.07.01", "Roof Engineering", "Roof (by area)", "m2", "area"),

        # Stair/Ramp
        ("IfcStairFlight",      "01.08.01", "Stair Engineering", "Stair Flight (by area)", "m2", "area"),
        ("IfcRampFlight",       "01.09.01", "Ramp Engineering", "Ramp (by area)", "m2", "area"),

        # Railing
        ("IfcRailing",          "02.01.01", "Components",   "Railing Handrail",       "m",  "length"),

        # Borehole/Pile (if exists)
        ("IfcBorehole",         "03.01.01", "Foundation Treatment", "Borehole Formation",       "m",  "length"),
        ("IfcBorehole",         "03.01.02", "Foundation Treatment", "Borehole Volume (reference)", "m3", "volume"),
        ("IfcBorehole",         "03.01.03", "Foundation Treatment", "Borehole Rebar (reference)", "t",  "rebar"),

        ("IfcPile",             "03.02.01", "Pile Foundation Engineering", "Pile Formation/Driving (by length)", "m", "length"),
        ("IfcPile",             "03.02.02", "Pile Foundation Engineering", "Pile Concrete (reference)", "m3", "volume"),
        ("IfcPile",             "03.02.03", "Pile Foundation Engineering", "Pile Rebar (reference)", "t",  "rebar"),
        ("IfcPile",             "03.02.04", "Pile Foundation Engineering", "Pile Earth Excavation (if applicable)", "m3", "earth_exc"),
        ("IfcPile",             "03.02.05", "Pile Foundation Engineering", "Pile Earth Backfill (if applicable)", "m3", "earth_bf"),

        # Opening deduction
        ("IfcOpeningElement",   "99.01.01", "Deduction Item",   "Opening Deduction",       "m2", "opening_deduct"),
    ],

    # Whether to ignore container-type objects like "IfcStair / IfcRamp" directly (to avoid 0-value pollution)
    "ignore_element_types": {"IfcStair", "IfcRamp"},
}


# =================================================
# Public API (DO NOT CHANGE FUNCTION NAMES)
# =================================================

def generateBill(ifc_path):
    """
    Entry function (interface name preserved)
    """
    if not os.path.exists(ifc_path):
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")

    ifc_file = ifcopenshell.open(ifc_path)

    project = ifc_file.by_type("IfcProject")[0]
    project_name = project.LongName if project.LongName else project.Name

    units = extract_units(ifc_file)


    components = get_component_quantities(ifc_file)


    boq_items = generate_professional_boq(ifc_file, components, units)

    project_info = {
        "projectName": project_name,
        "units": units,
        "components": components,
        "boq": boq_items,
    }

    project_info["markdown"] = generate_markdown(project_info)
    return project_info


def generate_boq_file(ifc_path, output_md_path="boq.md"):
    """
    Unified BOQ export interface (interface name preserved)
    """
    project_info = generateBill(ifc_path)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(project_info["markdown"])
    return output_md_path


# =================================================
# Component-level QTO
# =================================================

def get_component_quantities(ifc_file):
    """
    Extract quantities by element type / type object.
    - Prefer IfcElementQuantity (QTO)
    - Fallback to geometry
    - Aggregate by IfcTypeObject (If present) else element.is_a()
    """
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    combined = defaultdict(lambda: {
        "name": "",
        "count": 0,
        "volume": 0.0,
        "area": 0.0,
        "length": 0.0,
        "source": set(),
        "notes": set(),
    })

    for element in ifc_file.by_type("IfcElement"):
        etype = element.is_a()
        if etype in CONFIG["ignore_element_types"]:
            continue

        key = get_type_key(element)
        item = combined[key]
        item["name"] = key
        item["count"] += 1

        qto = read_ifc_qto(element)
        if qto:
            item["volume"] += qto.get("volume", 0.0)
            item["area"] += qto.get("area", 0.0)
            item["length"] += qto.get("length", 0.0)
            item["source"].add("QTO")
        else:
            geo = compute_geometry_qto(element, settings)
            item["volume"] += geo.get("volume", 0.0)
            item["area"] += geo.get("area", 0.0)
            item["length"] += geo.get("length", 0.0)
            item["source"].add("Geometry")
            if geo.get("open_mesh", False):
                item["notes"].add("OpenMesh(volume=0)")

    result = []
    for v in combined.values():
        result.append({
            "name": v["name"],
            "count": v["count"],
            "volume": round(v["volume"], 3),
            "area": round(v["area"], 3),
            "length": round(v["length"], 3),
            "source": ",".join(sorted(v["source"])),
            "notes": ",".join(sorted(v["notes"])) if v["notes"] else "",
        })


    result.sort(key=lambda x: x["name"])
    return result


# =================================================
# IFC helpers
# =================================================

def read_ifc_qto(element):
    """
    Read quantities from IfcElementQuantity
    """
    result = {"volume": 0.0, "area": 0.0, "length": 0.0}
    found = False

    for rel in getattr(element, "IsDefinedBy", []) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        prop_def = rel.RelatingPropertyDefinition
        if not prop_def or not prop_def.is_a("IfcElementQuantity"):
            continue


        for q in getattr(prop_def, "Quantities", []) or []:
            if q.is_a("IfcQuantityVolume"):
                result["volume"] += float(q.VolumeValue or 0.0)
                found = True
            elif q.is_a("IfcQuantityArea"):
                result["area"] += float(q.AreaValue or 0.0)
                found = True
            elif q.is_a("IfcQuantityLength"):
                result["length"] += float(q.LengthValue or 0.0)
                found = True

    return result if found else None


def get_type_key(element):
    """
    Use IfcTypeObject as aggregation key when present
    """
    for rel in getattr(element, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByType"):
            t = rel.RelatingType
            if t:
                return f"{t.is_a()}::{t.Name}"
    return element.is_a()


def extract_units(ifc_file):
    """
    Extract project units (length / area / volume)
    """
    units = {"length": None, "area": None, "volume": None}
    ua = ifc_file.by_type("IfcUnitAssignment")
    if not ua:
        return units

    for unit in ua[0].Units:
        if getattr(unit, "UnitType", None) == "LENGTHUNIT":
            units["length"] = getattr(unit, "Name", None)
        elif getattr(unit, "UnitType", None) == "AREAUNIT":
            units["area"] = getattr(unit, "Name", None)
        elif getattr(unit, "UnitType", None) == "VOLUMEUNIT":
            units["volume"] = getattr(unit, "Name", None)

    return units


# =================================================
# Geometry-based QTO (mesh)
# =================================================

def is_mesh_closed(faces):
    """
    Check if triangle mesh is closed (watertight-ish) by edge counting.
    faces: (n,3) int
    """
    edge_count = defaultdict(int)
    for a, b, c in faces:
        edges = ((a, b), (b, c), (c, a))
        for u, v in edges:
            if u > v:
                u, v = v, u
            edge_count[(u, v)] += 1
    return all(v == 2 for v in edge_count.values()) if edge_count else False


def compute_geometry_qto(element, settings):
    """
    Mesh-based QTO:
    - area: sum triangle areas
    - volume: signed tetrahedra volume (only meaningful when mesh is closed)
    - length: bbox longest dimension (heuristic)
    If mesh is open -> volume set to 0 and open_mesh flag set True
    """
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        geom = shape.geometry

        v = np.asarray(geom.verts, dtype=float).reshape((-1, 3))
        f = np.asarray(geom.faces, dtype=int).reshape((-1, 3))

        if v.size == 0 or f.size == 0:
            return {"volume": 0.0, "area": 0.0, "length": 0.0, "open_mesh": False}

        p1 = v[f[:, 0]]
        p2 = v[f[:, 1]]
        p3 = v[f[:, 2]]

        tri_areas = 0.5 * np.linalg.norm(np.cross(p2 - p1, p3 - p1), axis=1)
        area = float(tri_areas.sum())

        mins = v.min(axis=0)
        maxs = v.max(axis=0)
        dims = maxs - mins
        length = float(np.max(dims))

        closed = is_mesh_closed(f)
        if not closed:
            return {"volume": 0.0, "area": area, "length": length, "open_mesh": True}

        vol6 = np.einsum("ij,ij->i", p1, np.cross(p2, p3))
        volume = abs(float(vol6.sum())) / 6.0

        return {"volume": volume, "area": area, "length": length, "open_mesh": False}
    except Exception:
        return {"volume": 0.0, "area": 0.0, "length": 0.0, "open_mesh": False}



def steel_kg_per_m(d_mm: float) -> float:
    return 0.00617 * d_mm * d_mm


def compute_rebar_length_fallback(rebar_element, settings) -> float:
    try:
        shape = ifcopenshell.geom.create_shape(settings, rebar_element)
        geom = shape.geometry
        verts = geom.verts
        if not verts:
            return 0.0
        xs = verts[0::3]
        ys = verts[1::3]
        zs = verts[2::3]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)
        return float(max(dx, dy, dz))
    except Exception:
        return 0.0


def has_explicit_rebar(ifc_file) -> bool:
    return len(ifc_file.by_type("IfcReinforcingBar")) > 0 or len(ifc_file.by_type("IfcReinforcingMesh")) > 0


def get_explicit_rebar_summary(ifc_file, units):
    """
    Summarize IfcReinforcingBar:
    - Group by diameter: count / total_length(m) / total_weight(t)
    Note: The unit of NominalDiameter may be m or mm, here we do empirical conversion.
    """
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    bars = ifc_file.by_type("IfcReinforcingBar")
    out = defaultdict(lambda: {"count": 0, "length_m": 0.0, "weight_t": 0.0, "basis": "ExplicitRebar(Geometry)"})

    for b in bars:
        d = float(getattr(b, "NominalDiameter", 0.0) or 0.0)

        # Empirical: if d < 0.1, consider as "meter" -> convert to millimeter
        if d > 0.0 and d < 0.1:
            d_mm = d * 1000.0
        else:
            d_mm = d

        length_m = compute_rebar_length_fallback(b, settings)
        kgpm = steel_kg_per_m(d_mm)
        weight_t = (length_m * kgpm) / 1000.0

        key = f"Rebar φ{int(round(d_mm))}mm"
        out[key]["count"] += 1
        out[key]["length_m"] += length_m
        out[key]["weight_t"] += weight_t

    # Reinforcement mesh: here only count the quantity, weight needs more parameters (spacing/diameter/dimensions)
    meshes = ifc_file.by_type("IfcReinforcingMesh")
    if meshes:
        key = "Reinforcement Mesh (specification needed)"
        out[key]["count"] += len(meshes)
        out[key]["basis"] = "ExplicitRebar(Mesh)"

    result = []
    for k, v in out.items():
        result.append({
            "name": k,
            "count": v["count"],
            "length_m": round(v["length_m"], 3),
            "weight_t": round(v["weight_t"], 6),
            "basis": v["basis"],
        })
    result.sort(key=lambda x: x["name"])
    return result


def estimate_rebar_t_by_ratio(element_ifc_type: str, concrete_volume_m3: float) -> float:
    ratio = CONFIG["rebar_ratio_kg_per_m3"].get(element_ifc_type, 0.0)
    kg = ratio * concrete_volume_m3
    return kg / 1000.0  # t


# =================================================
# Earthwork & Formwork
# =================================================

def calc_earth_excavation_m3(concrete_volume_m3: float) -> float:
    f = CONFIG["earthwork"]["excavation_factor"]
    return concrete_volume_m3 * f


def calc_earth_backfill_m3(concrete_volume_m3: float) -> float:
    exc = calc_earth_excavation_m3(concrete_volume_m3)
    bf = max(exc - concrete_volume_m3, 0.0)
    return bf * CONFIG["earthwork"]["backfill_factor"]


def calc_formwork_m2(element_ifc_type: str, surface_area_m2: float) -> float:
    factor = CONFIG["formwork"]["factor_by_type"].get(element_ifc_type, CONFIG["formwork"]["factor_default"])
    return surface_area_m2 * factor


# =================================================
# BOQ generation
# =================================================

def match_boq_rules(component_name: str):
    """
    component_name maybe:
    - IfcBeam
    - IfcColumnType::W250X67
    """
    rules = []
    for prefix, code, part, item, unit, calc in CONFIG["boq_map"]:
        if prefix.endswith("::"):
            if component_name.startswith(prefix):
                rules.append((code, part, item, unit, calc, prefix))
        else:
            if component_name == prefix:
                rules.append((code, part, item, unit, calc, prefix))
    return rules


def generate_professional_boq(ifc_file, components, units):
    """
    Create professional BOQ items:
    - From components: concrete / formwork / earthwork / length / area etc.
    - From explicit rebar (IfcReinforcingBar): separate rebar summary
    - Opening: deduct
    """

    comp_index = {c["name"]: c for c in components}


    explicit = has_explicit_rebar(ifc_file)
    explicit_rebar = get_explicit_rebar_summary(ifc_file, units) if explicit else []

    boq = defaultdict(lambda: {
        "code": "",
        "part": "",
        "item": "",
        "unit": "",
        "quantity": 0.0,
        "basis": set(),
        "components": set(),
    })

    for comp_name, c in comp_index.items():
        rules = match_boq_rules(comp_name)
        if not rules:
            continue


        base_type = comp_name.split("::", 1)[0]

        for code, part, item, unit, calc, _prefix in rules:
            qty = 0.0

            if calc == "volume":
                qty = c["volume"]
            elif calc == "area":
                qty = c["area"]
            elif calc == "length":
                qty = c["length"]

            elif calc == "formwork":
                qty = calc_formwork_m2(base_type, c["area"])

            elif calc == "earth_exc":
                if base_type in CONFIG["earthwork"]["apply_to_types"]:
                    qty = calc_earth_excavation_m3(c["volume"])
                else:
                    qty = 0.0

            elif calc == "earth_bf":
                if base_type in CONFIG["earthwork"]["apply_to_types"]:
                    qty = calc_earth_backfill_m3(c["volume"])
                else:
                    qty = 0.0

            elif calc == "opening_deduct":

                deduct_by = CONFIG["openings"]["deduct_by"]
                if deduct_by == "volume":
                    qty = -abs(c["volume"])
                    unit = units["volume"] or "m3"
                else:
                    qty = -abs(c["area"])
                    unit = CONFIG["openings"]["unit"]

            elif calc == "rebar":

                if explicit:
                    qty = 0.0
                else:
                    qty = estimate_rebar_t_by_ratio(base_type, c["volume"])

            elif calc == "composite_column":
   
                if unit == "-":
                    continue
                qty = c["length"]

            else:
                qty = 0.0

            k = (code, item, unit)
            boq[k]["code"] = code
            boq[k]["part"] = part
            boq[k]["item"] = item
            boq[k]["unit"] = unit
            boq[k]["quantity"] += float(qty or 0.0)
            boq[k]["basis"].add(c["source"])
            if c.get("notes"):
                boq[k]["basis"].add(c["notes"])
            boq[k]["components"].add(comp_name)

    if explicit_rebar:

        for r in explicit_rebar:
            code = "04.01.01"
            part = "钢筋工程"
            item = r["name"]
            unit = "t"
            qty = r["weight_t"]

            k = (code, item, unit)
            boq[k]["code"] = code
            boq[k]["part"] = part
            boq[k]["item"] = item
            boq[k]["unit"] = unit
            boq[k]["quantity"] += float(qty or 0.0)
            boq[k]["basis"].add(r["basis"])
            boq[k]["components"].add("IfcReinforcingBar")

    result = []
    for (_k), v in boq.items():
        result.append({
            "code": v["code"],
            "part": v["part"],
            "item": v["item"],
            "unit": v["unit"],
            "quantity": round(v["quantity"], 3),
            "basis": ";".join(sorted({b for b in v["basis"] if b})),
            "components": ", ".join(sorted(v["components"]))[:4000],
        })

    result.sort(key=lambda x: (x["code"], x["part"], x["item"]))
    return result


# =================================================
# Markdown rendering (Bill of Quantities + Component Summary)
# =================================================

def generate_markdown(info):
    md = []
    md.append("# Bill of Quantities (BOQ)\n")
    md.append(f"**Project Name：** {info['projectName']}\n")

    md.append("## Model Units")
    md.append(f"- Length：{info['units'].get('length')}")
    md.append(f"- Area：{info['units'].get('area')}")
    md.append(f"- Volume：{info['units'].get('volume')}\n")

    md.append("## BOQ Details (Work Content)")
    md.append("| Code | Main Division | Sub Division | Unit | Quantity | Measurement Basis | Source Components (Aggregated Key) |")
    md.append("|---|---|---|---:|---:|---|---|")
    for r in info["boq"]:
        md.append(
            f"| {r['code']} | {r['part']} | {r['item']} | {r['unit']} | "
            f"{r['quantity']} | {r['basis']} | {r['components']} |"
        )

    md.append("\n## Component Summary (for Verification)")
    md.append("| Component Type/Type Object | Count | Volume | Area | Length | Source | Notes |")
    md.append("|---|---:|---:|---:|---:|---|---|")
    for c in info["components"]:
        md.append(
            f"| {c['name']} | {c['count']} | {c['volume']} | {c['area']} | {c['length']} | {c['source']} | {c.get('notes','')} |"
        )

    md.append("\n## Notes (Important)")
    md.append("- Volume calculation by geometric method is sensitive to non-closed meshes: When the program detects an open mesh, the volume is set to 0 and the note `OpenMesh(volume=0)` is added to avoid unrealistic volume values.")
    md.append("- Template/Earthwork/Reinforcement content estimation belongs to engineering rule parameters, which have been centralized in CONFIG and can be adjusted according to project requirements.")
    md.append("- If IFC contains detailed reinforcement (IfcReinforcingBar), rebar is counted by diameter categories; otherwise, estimated by reinforcement content (kg/m³).")
    md.append("- Openings (IfcOpeningElement) are by default deducted as negative values based on area, with actual deduction criteria subject to project measurement rules.")

    return "\n".join(md)
