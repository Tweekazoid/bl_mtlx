#!/usr/bin/env python3
"""MaterialX -> Blender importer.

Reads a MaterialX (.mtlx) document and rebuilds the material(s) as a Blender
Principled BSDF node network. Supports the standard_surface, open_pbr_surface
and UsdPreviewSurface shading models, and attempts to translate every upstream
node in the referenced node graphs, reporting any nodes it cannot map.

Usage:
    import materialx_importer as mtlx_importer
    result = mtlx_importer.import_materialx_to_blender("input.mtlx", logger)
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

import bpy  # type: ignore
import MaterialX as mx  # type: ignore # noqa: N813

# --- Principled BSDF socket candidates (handles Blender 3.x / 4.x renames) ---
_PRINCIPLED_SOCKETS: dict[str, list[str]] = {
    "baseColor": ["Base Color"],
    "metallic": ["Metallic"],
    "roughness": ["Roughness"],
    "specularLevel": ["Specular IOR Level", "Specular"],
    "specularTint": ["Specular Tint"],
    "ior": ["IOR"],
    "transmission": ["Transmission Weight", "Transmission"],
    "alpha": ["Alpha"],
    "normal": ["Normal"],
    "emissionColor": ["Emission Color", "Emission"],
    "emissionStrength": ["Emission Strength"],
    "subsurface": ["Subsurface Weight", "Subsurface"],
    "subsurfaceRadius": ["Subsurface Radius"],
    "subsurfaceScale": ["Subsurface Scale"],
    "subsurfaceAnisotropy": ["Subsurface Anisotropy"],
    "sheen": ["Sheen Weight", "Sheen"],
    "sheenTint": ["Sheen Tint"],
    "sheenRoughness": ["Sheen Roughness"],
    "coat": ["Coat Weight", "Clearcoat"],
    "coatTint": ["Coat Tint"],
    "coatRoughness": ["Coat Roughness", "Clearcoat Roughness"],
    "coatIor": ["Coat IOR"],
    "coatNormal": ["Coat Normal", "Clearcoat Normal"],
    "anisotropic": ["Anisotropic"],
    "anisotropicRotation": ["Anisotropic Rotation"],
}

# --- Surface-shader input -> Principled socket key, per shading model ---
_STANDARD_SURFACE_MAP: dict[str, str] = {
    "base_color": "baseColor",
    "metalness": "metallic",
    "specular_roughness": "roughness",
    "specular": "specularLevel",
    "specular_color": "specularTint",
    "specular_IOR": "ior",
    "transmission": "transmission",
    "opacity": "alpha",
    "normal": "normal",
    "emission_color": "emissionColor",
    "emission": "emissionStrength",
    "emission_strength": "emissionStrength",
    "subsurface": "subsurface",
    "subsurface_radius": "subsurfaceRadius",
    "subsurface_scale": "subsurfaceScale",
    "subsurface_anisotropy": "subsurfaceAnisotropy",
    "sheen": "sheen",
    "sheen_color": "sheenTint",
    "sheen_roughness": "sheenRoughness",
    "coat": "coat",
    "coat_color": "coatTint",
    "coat_roughness": "coatRoughness",
    "coat_IOR": "coatIor",
    "coat_normal": "coatNormal",
    "specular_anisotropy": "anisotropic",
    "specular_rotation": "anisotropicRotation",
}

_OPEN_PBR_MAP: dict[str, str] = {
    "base_color": "baseColor",
    "base_metalness": "metallic",
    "specular_weight": "specularLevel",
    "specular_color": "specularTint",
    "specular_roughness": "roughness",
    "specular_ior": "ior",
    "transmission_weight": "transmission",
    "subsurface_weight": "subsurface",
    "subsurface_radius": "subsurfaceRadius",
    "coat_weight": "coat",
    "coat_color": "coatTint",
    "coat_roughness": "coatRoughness",
    "coat_ior": "coatIor",
    "fuzz_weight": "sheen",
    "fuzz_color": "sheenTint",
    "fuzz_roughness": "sheenRoughness",
    "emission_color": "emissionColor",
    "emission_luminance": "emissionStrength",
    "geometry_normal": "normal",
    "geometry_coat_normal": "coatNormal",
    "geometry_opacity": "alpha",
}

_USD_PREVIEW_MAP: dict[str, str] = {
    "diffuseColor": "baseColor",
    "emissiveColor": "emissionColor",
    "specularColor": "specularTint",
    "metallic": "metallic",
    "roughness": "roughness",
    "clearcoat": "coat",
    "clearcoatRoughness": "coatRoughness",
    "opacity": "alpha",
    "ior": "ior",
    "normal": "normal",
}

_GLTF_PBR_MAP: dict[str, str] = {
    "base_color": "baseColor",
    "metallic": "metallic",
    "roughness": "roughness",
    "normal": "normal",
    "emissive": "emissionColor",
    "emissive_strength": "emissionStrength",
    "alpha": "alpha",
    "transmission": "transmission",
    "ior": "ior",
    "clearcoat": "coat",
    "clearcoat_roughness": "coatRoughness",
    "clearcoat_normal": "coatNormal",
    "sheen_color": "sheenTint",
    "sheen_roughness": "sheenRoughness",
}

_SHADER_MAPS: dict[str, dict[str, str]] = {
    "standard_surface": _STANDARD_SURFACE_MAP,
    "open_pbr_surface": _OPEN_PBR_MAP,
    "UsdPreviewSurface": _USD_PREVIEW_MAP,
    "gltf_pbr": _GLTF_PBR_MAP,
}

# Shader inputs that have no clean Principled BSDF equivalent. These are dropped
# quietly rather than reported as "unsupported", to keep the report meaningful.
_IGNORED_SHADER_INPUTS: frozenset[str] = frozenset(
    {
        "base",
        "base_weight",
        "diffuse_roughness",
        "thin_walled",
        "thin_film_thickness",
        "thin_film_IOR",
        "thin_film_weight",
        "tangent",
        "coat_affect_color",
        "coat_affect_roughness",
        "transmission_color",
        "transmission_depth",
        "transmission_scatter",
        "transmission_scatter_anisotropy",
        "transmission_dispersion",
        "transmission_extra_roughness",
        "subsurface_color",
        "occlusion",
        "geometry_tangent",
        "emission_luminance",
        "displacement",
    },
)

# --- Math category -> (Blender scalar op, Blender vector op or None) ---
_MATH_OPS: dict[str, tuple[str | None, str | None]] = {
    "add": ("ADD", "ADD"),
    "subtract": ("SUBTRACT", "SUBTRACT"),
    "multiply": ("MULTIPLY", "MULTIPLY"),
    "divide": ("DIVIDE", "DIVIDE"),
    "modulo": ("MODULO", None),
    "power": ("POWER", None),
    "min": ("MINIMUM", "MINIMUM"),
    "max": ("MAXIMUM", "MAXIMUM"),
    "absval": ("ABSOLUTE", "ABSOLUTE"),
    "floor": ("FLOOR", "FLOOR"),
    "ceil": ("CEIL", "CEIL"),
    "round": ("ROUND", None),
    "sign": ("SIGN", None),
    "sin": ("SINE", "SINE"),
    "cos": ("COSINE", "COSINE"),
    "tan": ("TANGENT", "TANGENT"),
    "asin": ("ARCSINE", None),
    "acos": ("ARCCOSINE", None),
    "atan2": ("ARCTAN2", None),
    "sqrt": ("SQRT", None),
    "ln": ("LOGARITHM", None),
    "normalize": (None, "NORMALIZE"),
    "magnitude": (None, "LENGTH"),
    "dotproduct": (None, "DOT_PRODUCT"),
    "crossproduct": (None, "CROSS_PRODUCT"),
    "distance": (None, "DISTANCE"),
}


# --- Procedural / noise node registry (mtlx category -> closest Blender node) ---
# Each entry describes how to build a Blender texture node for a MaterialX
# procedural node. Fields:
#   bl        : primary Blender node bl_idname
#   fallback  : node to use when `bl` is unavailable in this Blender version
#   out       : ordered output-socket candidates (first present one is used)
#   inputs    : {mtlx_input: bl_socket_candidate(s)} - missing sockets are skipped
#   props     : node attributes to set (silently ignored if absent, e.g. old versions)
# Add an entry here to expand coverage; no other code changes are needed.
_PROC_NODES: dict[str, dict[str, Any]] = {
    # Perlin / fBm noise -> Blender Noise Texture
    "noise2d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
            "lacunarity": ["Lacunarity"],
            "diminish": ["Roughness"],
            "roughness": ["Roughness"],
        },
    },
    "noise3d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
            "lacunarity": ["Lacunarity"],
            "diminish": ["Roughness"],
            "roughness": ["Roughness"],
        },
    },
    "fractal2d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
            "lacunarity": ["Lacunarity"],
            "diminish": ["Roughness"],
            "roughness": ["Roughness"],
        },
    },
    "fractal3d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
            "lacunarity": ["Lacunarity"],
            "diminish": ["Roughness"],
            "roughness": ["Roughness"],
        },
    },
    # Unified noise selector -> generic Noise Texture (closest overall match)
    "unifiednoise2d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
        },
    },
    "unifiednoise3d": {
        "bl": "ShaderNodeTexNoise",
        "out": ["Fac", "Color"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "octaves": ["Detail"],
            "detail": ["Detail"],
        },
    },
    # Worley (distance) noise -> Voronoi Distance
    "worleynoise2d": {
        "bl": "ShaderNodeTexVoronoi",
        "out": ["Distance", "Color"],
        "props": {"voronoi_dimensions": "2D"},
        "inputs": {"texcoord": ["Vector"], "position": ["Vector"], "jitter": ["Randomness"]},
    },
    "worleynoise3d": {
        "bl": "ShaderNodeTexVoronoi",
        "out": ["Distance", "Color"],
        "props": {"voronoi_dimensions": "3D"},
        "inputs": {"texcoord": ["Vector"], "position": ["Vector"], "jitter": ["Randomness"]},
    },
    # Cell noise (random value per cell) -> Voronoi Color
    "cellnoise2d": {
        "bl": "ShaderNodeTexVoronoi",
        "out": ["Color", "Distance"],
        "props": {"voronoi_dimensions": "2D"},
        "inputs": {"texcoord": ["Vector"], "position": ["Vector"]},
    },
    "cellnoise3d": {
        "bl": "ShaderNodeTexVoronoi",
        "out": ["Color", "Distance"],
        "props": {"voronoi_dimensions": "3D"},
        "inputs": {"texcoord": ["Vector"], "position": ["Vector"]},
    },
    # Our exporter's non-standard Voronoi node -> Voronoi
    "voronoi": {
        "bl": "ShaderNodeTexVoronoi",
        "out": ["Distance", "Color"],
        "inputs": {"texcoord": ["Vector"], "position": ["Vector"], "scale": ["Scale"], "detail": ["Detail"]},
    },
    # Random hash -> White Noise Texture
    "randomfloat": {
        "bl": "ShaderNodeTexWhiteNoise",
        "out": ["Value", "Color"],
        "inputs": {"in": ["Vector"], "texcoord": ["Vector"], "position": ["Vector"]},
    },
    "randomcolor": {
        "bl": "ShaderNodeTexWhiteNoise",
        "out": ["Color", "Value"],
        "inputs": {"in": ["Vector"], "texcoord": ["Vector"], "position": ["Vector"]},
    },
    # Our exporter's non-standard Wave node -> Wave Texture
    "wave": {
        "bl": "ShaderNodeTexWave",
        "out": ["Color", "Fac"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "distortion": ["Distortion"],
            "detail": ["Detail"],
        },
    },
    # Musgrave (removed in Blender 4.1) -> Musgrave, else Noise as closest match
    "musgrave": {
        "bl": "ShaderNodeTexMusgrave",
        "fallback": "ShaderNodeTexNoise",
        "out": ["Height", "Fac"],
        "inputs": {
            "texcoord": ["Vector"],
            "position": ["Vector"],
            "scale": ["Scale"],
            "detail": ["Detail"],
            "dimension": ["Dimension"],
            "lacunarity": ["Lacunarity"],
        },
    },
}


class MaterialXImporter:
    """Builds Blender materials from a MaterialX document."""

    def __init__(self, filepath: str, logger, options: dict | None = None) -> None:
        self.filepath = filepath
        self.logger = logger
        self.options = options or {}
        self.doc = mx.createDocument()
        self.unsupported: list[dict[str, str]] = []
        # Per-material state (reset for each material):
        self.node_tree = None
        self._built: dict[str, tuple[Any, Any]] = {}  # mtlx node name -> (bl_node, out_socket)
        self._depth_cursor: dict[int, float] = {}

    # ------------------------------------------------------------------ read
    def read(self) -> None:
        mx.readFromXmlFile(self.doc, self.filepath)

    def _shader_nodes(self) -> list:
        """Return (material_node_or_None, shader_node) pairs to import."""
        pairs: list[tuple[Any, Any]] = []
        seen: set[str] = set()
        for mat in self.doc.getMaterialNodes():
            surf = mat.getInput("surfaceshader")
            shader = surf.getConnectedNode() if surf is not None else None
            if shader is not None:
                pairs.append((mat, shader))
                seen.add(shader.getName())
        # Standalone surface shaders not referenced by a material node.
        for node in self.doc.getNodes():
            if node.getType() == "surfaceshader" and node.getName() not in seen:
                pairs.append((None, node))
        return pairs

    # ----------------------------------------------------------------- import
    def run(self) -> dict[str, Any]:
        self.read()
        pairs = self._shader_nodes()
        if not pairs:
            return {
                "success": False,
                "error": "No surface material found in the MaterialX document.",
                "materials": [],
                "unsupported_nodes": [],
            }

        created: list[str] = []
        for mat_node, shader in pairs:
            name = (mat_node.getName() if mat_node is not None else shader.getName()) or "MaterialX"
            self._import_one(name, mat_node, shader)
            created.append(name)

        return {
            "success": True,
            "materials": created,
            "unsupported_nodes": self.unsupported,
        }

    def _import_one(self, name: str, mat_node, shader) -> None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nt = mat.node_tree
        self.node_tree = nt
        self._built = {}
        self._depth_cursor = {}
        nt.nodes.clear()

        output = nt.nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        principled = nt.nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        nt.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        category = shader.getCategory()
        input_map = _SHADER_MAPS.get(category)
        if input_map is None:
            # Unknown shading model: still try standard_surface names as a best effort.
            input_map = _STANDARD_SURFACE_MAP
            self.unsupported.append(
                {
                    "name": shader.getName(),
                    "category": category,
                    "reason": "unknown shading model (used standard_surface mapping)",
                },
            )

        for inp in shader.getActiveInputs():
            self._apply_shader_input(principled, input_map, inp)

        if mat_node is not None:
            self._apply_displacement(nt, output, mat_node)
        # UsdPreviewSurface carries displacement on the shader itself.
        if category == "UsdPreviewSurface":
            disp_in = shader.getInput("displacement")
            if disp_in is not None:
                self._connect_displacement_socket(nt, output, disp_in)

    # ------------------------------------------------------- shader input glue
    def _apply_shader_input(self, principled, input_map: dict[str, str], inp) -> None:
        mtlx_name = inp.getName()
        socket_key = input_map.get(mtlx_name)
        if socket_key is None:
            if mtlx_name not in _IGNORED_SHADER_INPUTS:
                self.unsupported.append(
                    {
                        "name": principled.name,
                        "category": "surface_input",
                        "reason": f"unmapped shader input '{mtlx_name}'",
                    },
                )
            return

        socket = self._find_socket(principled.inputs, _PRINCIPLED_SOCKETS.get(socket_key, []))
        if socket is None:
            return

        src = self._resolve(inp)
        if src is None:
            return
        kind, payload, out_name = src
        if kind == "node":
            built = self._build(payload, depth=1)
            if built is not None:
                bl_node, out_socket = built
                chosen = self._pick_output(bl_node, out_name) or out_socket
                if chosen is not None:
                    self.node_tree.links.new(chosen, socket)
        else:  # value
            self._set_socket_value(socket, payload, inp.getType())
        # Emission needs a non-zero strength to show up if only color was provided.
        if socket_key == "emissionColor":
            strength = self._find_socket(principled.inputs, _PRINCIPLED_SOCKETS["emissionStrength"])
            if strength is not None and strength.default_value == 0.0:
                strength.default_value = 1.0

    # ----------------------------------------------------------- node building
    def _build(self, node, depth: int):
        """Recursively build a Blender node for an mtlx node. Returns (bl_node, out_socket)."""
        key = node.getName()
        if key in self._built:
            return self._built[key]

        category = node.getCategory()

        handler = getattr(self, f"_h_{category}", None)
        if handler is not None:
            result = handler(node, depth)
        elif category in _PROC_NODES:
            result = self._build_proc(node, depth, _PROC_NODES[category])
        elif category in _MATH_OPS:
            result = self._build_math(node, depth)
        else:
            result = self._build_unsupported(node, depth)

        if result is not None:
            bl_node = result[0]
            bl_node.location = self._place(depth)
            self._built[key] = result
        return result

    def _build_inputs(self, node, bl_node, mapping: dict[str, Any], depth: int) -> None:
        """Wire an mtlx node's inputs into a blender node using {mtlx_input: bl_socket_name(s)_or_index}."""
        for inp in node.getActiveInputs():
            target = mapping.get(inp.getName())
            if target is None:
                continue
            socket = self._input_socket(bl_node, target)
            if socket is None:
                continue
            src = self._resolve(inp)
            if src is None:
                continue
            kind, payload, out_name = src
            if kind == "node":
                built = self._build(payload, depth + 1)
                if built is not None:
                    chosen = self._pick_output(built[0], out_name) or built[1]
                    if chosen is not None:
                        self.node_tree.links.new(chosen, socket)
            else:
                self._set_socket_value(socket, payload, inp.getType())

    # --- specific node handlers (category name after _h_) ---
    def _h_image(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeTexImage")
        file_in = node.getInput("file")
        if file_in is not None:
            self._load_image(bl, file_in.getValueString() or "", node)
        tex = node.getInput("texcoord")
        if tex is not None:
            src = self._resolve(tex)
            if src is not None and src[0] == "node":
                built = self._build(src[1], depth + 1)
                if built is not None:
                    self.node_tree.links.new(built[1], bl.inputs["Vector"])
        return bl, bl.outputs["Color"]

    _h_tiledimage = _h_image
    _h_gltf_colorimage = _h_image
    _h_gltf_image = _h_image

    def _h_constant(self, node, depth):  # noqa: ARG002
        val_in = node.getInput("value")
        node_type = node.getType()
        if node_type in ("color3", "color4"):
            bl = self.node_tree.nodes.new("ShaderNodeRGB")
            if val_in is not None and val_in.getValue() is not None:
                self._set_socket_value(bl.outputs["Color"], val_in.getValue(), node_type)
            return bl, bl.outputs["Color"]
        bl = self.node_tree.nodes.new("ShaderNodeValue")
        if val_in is not None and val_in.getValue() is not None:
            self._set_socket_value(bl.outputs["Value"], val_in.getValue(), node_type)
        return bl, bl.outputs["Value"]

    def _h_normalmap(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeNormalMap")
        self._build_inputs(node, bl, {"in": "Color", "scale": "Strength"}, depth)
        return bl, bl.outputs["Normal"]

    _h_gltf_normalmap = _h_normalmap

    def _h_bump(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeBump")
        self._build_inputs(node, bl, {"height": "Height", "scale": "Strength", "normal": "Normal"}, depth)
        return bl, bl.outputs["Normal"]

    def _h_UsdTransform2d(self, node, depth):  # noqa: N802
        bl = self.node_tree.nodes.new("ShaderNodeMapping")
        self._build_inputs(
            node,
            bl,
            {"in": "Vector", "translation": "Location", "rotation": "Rotation", "scale": "Scale"},
            depth,
        )
        return bl, bl.outputs["Vector"]

    _h_transform2d = _h_UsdTransform2d
    _h_place2d = _h_UsdTransform2d

    def _h_mix(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeMixRGB")
        self._build_inputs(node, bl, {"fg": "Color1", "bg": "Color2", "mix": "Fac"}, depth)
        return bl, bl.outputs["Color"]

    def _h_separate3(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeSeparateColor")
        self._build_inputs(node, bl, {"in": "Color"}, depth)
        return bl, bl.outputs["Red"]

    def _h_combine3(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeCombineColor")
        self._build_inputs(node, bl, {"in1": "Red", "in2": "Green", "in3": "Blue"}, depth)
        return bl, bl.outputs["Color"]

    def _h_invert(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeInvert")
        self._build_inputs(node, bl, {"in": "Color", "amount": "Fac"}, depth)
        return bl, bl.outputs["Color"]

    def _h_clamp(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeClamp")
        self._build_inputs(node, bl, {"in": "Value", "low": "Min", "high": "Max"}, depth)
        return bl, bl.outputs["Result"]

    def _h_remap(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeMapRange")
        self._build_inputs(
            node,
            bl,
            {"in": "Value", "inlow": "From Min", "inhigh": "From Max", "outlow": "To Min", "outhigh": "To Max"},
            depth,
        )
        return bl, bl.outputs["Result"]

    _h_range = _h_remap

    def _h_luminance(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeRGBToBW")
        self._build_inputs(node, bl, {"in": "Color"}, depth)
        return bl, bl.outputs["Val"]

    def _h_checkerboard(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeTexChecker")
        self._build_inputs(node, bl, {"texcoord": "Vector", "in1": "Color1", "in2": "Color2"}, depth)
        return bl, bl.outputs["Color"]

    def _h_ramplr(self, node, depth):
        return self._build_ramp(node, depth, component=0)

    def _h_ramptb(self, node, depth):
        return self._build_ramp(node, depth, component=1)

    def _build_ramp(self, node, depth, component: int):
        """ramplr/ramptb: linear blend of valuel/valuer across a texcoord axis."""
        mix = self.node_tree.nodes.new("ShaderNodeMixRGB")
        self._build_inputs(node, mix, {"valuel": "Color1", "valuer": "Color2"}, depth)
        sep = self.node_tree.nodes.new("ShaderNodeSeparateXYZ")
        tc_in = node.getInput("texcoord")
        src = self._resolve(tc_in) if tc_in is not None else None
        if src is not None and src[0] == "node":
            built = self._build(src[1], depth + 1)
            if built is not None:
                self.node_tree.links.new(built[1], sep.inputs["Vector"])
        else:
            tex = self.node_tree.nodes.new("ShaderNodeTexCoord")
            self.node_tree.links.new(tex.outputs["UV"], sep.inputs["Vector"])
        self.node_tree.links.new(sep.outputs[component], mix.inputs["Fac"])
        return mix, mix.outputs["Color"]

    def _h_ramp(self, node, depth):  # noqa: C901
        """MaterialX 'ramp' (the exporter's ColorRamp encoding) -> Blender ColorRamp node."""
        bl = self._new("ShaderNodeValToRGB")
        if bl is None:
            return self._build_unsupported(node, depth)
        ramp = bl.color_ramp

        positions: dict[int, float] = {}
        colors: dict[int, list[float]] = {}
        interpolation = None
        for inp in node.getActiveInputs():
            name = inp.getName()
            if name == "interpolation":
                val = inp.getValue()
                interpolation = int(val) if val is not None else None
            elif name.startswith("interval"):
                idx = self._ramp_index(name, "interval")
                val = inp.getValue()
                if idx is not None and val is not None:
                    positions[idx] = float(val)
            elif name.startswith("color"):
                idx = self._ramp_index(name, "color")
                comps = self._to_components(inp.getValue(), inp.getType())
                if idx is not None and comps:
                    colors[idx] = comps

        # Wire the driving factor (exported as the ramp's 'texcoord' input) into Fac.
        tc_in = node.getInput("texcoord")
        if tc_in is not None:
            src = self._resolve(tc_in)
            if src is not None and src[0] == "node":
                built = self._build(src[1], depth + 1)
                if built is not None:
                    self.node_tree.links.new(built[1], bl.inputs["Fac"])

        # Export collapsed EASE/CARDINAL/B_SPLINE to 1; restore the closest matches.
        if interpolation is not None:
            ramp.interpolation = {0: "LINEAR", 2: "CONSTANT"}.get(interpolation, "B_SPLINE")

        indices = sorted(set(colors) | set(positions))
        if indices:
            need = max(1, len(indices))
            while len(ramp.elements) < need:
                ramp.elements.new(1.0)
            while len(ramp.elements) > need:
                ramp.elements.remove(ramp.elements[-1])
            # Assign in ascending position order so Blender's auto-sort stays stable.
            for slot, idx in enumerate(indices):
                element = ramp.elements[slot]
                if idx in positions:
                    element.position = positions[idx]
                comps = colors.get(idx)
                if comps:
                    rgba = list(comps[:4])
                    while len(rgba) < 3:
                        rgba.append(0.0)
                    if len(rgba) == 3:
                        rgba.append(1.0)
                    element.color = rgba[:4]
        return bl, bl.outputs["Color"]

    @staticmethod
    def _ramp_index(name: str, prefix: str) -> int | None:
        try:
            return int(name[len(prefix) :])
        except ValueError:
            return None

    # --- generic procedural node builder (table-driven, see _PROC_NODES) ---
    def _build_proc(self, node, depth, spec: dict[str, Any]):
        bl = self._new(spec["bl"], spec.get("fallback"))
        if bl is None:
            return self._build_unsupported(node, depth)
        for attr, val in spec.get("props", {}).items():
            with contextlib.suppress(TypeError, ValueError, AttributeError):
                setattr(bl, attr, val)
        self._build_inputs(node, bl, spec["inputs"], depth)
        return bl, self._first_output(bl, spec["out"])

    def _h_texcoord(self, node, depth):  # noqa: ARG002
        bl = self.node_tree.nodes.new("ShaderNodeTexCoord")
        return bl, bl.outputs["UV"]

    _h_geompropvalue = _h_texcoord

    def _h_position(self, node, depth):  # noqa: ARG002
        bl = self.node_tree.nodes.new("ShaderNodeNewGeometry")
        return bl, bl.outputs["Position"]

    def _h_normal(self, node, depth):  # noqa: ARG002
        bl = self.node_tree.nodes.new("ShaderNodeNewGeometry")
        return bl, bl.outputs["Normal"]

    def _h_tangent(self, node, depth):  # noqa: ARG002
        bl = self.node_tree.nodes.new("ShaderNodeNewGeometry")
        return bl, bl.outputs["Tangent"]

    def _h_convert(self, node, depth):
        """Type conversion: pass the source straight through (Blender auto-converts)."""
        for inp in node.getActiveInputs():
            src = self._resolve(inp)
            if src is not None and src[0] == "node":
                return self._build(src[1], depth)
        return self._build_unsupported(node, depth)

    def _h_extract(self, node, depth):
        bl = self.node_tree.nodes.new("ShaderNodeSeparateColor")
        self._build_inputs(node, bl, {"in": "Color"}, depth)
        index_in = node.getInput("index")
        idx = 0
        if index_in is not None and index_in.getValue() is not None:
            try:
                idx = int(index_in.getValue())
            except (TypeError, ValueError):
                idx = 0
        out = bl.outputs[min(max(idx, 0), 2)]
        return bl, out

    # --- generic math ---
    def _build_math(self, node, depth):
        category = node.getCategory()
        scalar_op, vector_op = _MATH_OPS[category]
        is_vector = node.getType().startswith("vector")
        if is_vector and vector_op is not None:
            bl = self.node_tree.nodes.new("ShaderNodeVectorMath")
            bl.operation = vector_op
            out = (
                bl.outputs["Vector"] if vector_op not in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else bl.outputs["Value"]
            )
        elif scalar_op is not None:
            bl = self.node_tree.nodes.new("ShaderNodeMath")
            bl.operation = scalar_op
            out = bl.outputs["Value"]
        else:
            return self._build_unsupported(node, depth)
        # mtlx math inputs: in1 -> socket 0, in2 -> socket 1
        self._build_inputs(node, bl, {"in1": 0, "in2": 1, "in": 0, "amount": 1}, depth)
        return bl, out

    def _build_unsupported(self, node, depth):  # noqa: ARG002
        """Fallback: emit a constant carrying the node's default value so the graph stays valid."""
        self.unsupported.append(
            {"name": node.getName(), "category": node.getCategory(), "reason": "no Blender equivalent"},
        )
        node_type = node.getType()
        if node_type in ("color3", "color4"):
            bl = self.node_tree.nodes.new("ShaderNodeRGB")
            bl.label = f"[unsupported] {node.getCategory()}"
            return bl, bl.outputs["Color"]
        bl = self.node_tree.nodes.new("ShaderNodeValue")
        bl.label = f"[unsupported] {node.getCategory()}"
        return bl, bl.outputs["Value"]

    # ----------------------------------------------------------- displacement
    def _apply_displacement(self, nt, output, mat_node) -> None:
        disp_in = mat_node.getInput("displacementshader")
        if disp_in is None:
            return
        shader = disp_in.getConnectedNode()
        if shader is None:
            return
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.location = (0, -400)
        self._build_inputs(shader, disp, {"displacement": "Height", "scale": "Scale"}, 1)
        nt.links.new(disp.outputs["Displacement"], output.inputs["Displacement"])

    def _connect_displacement_socket(self, nt, output, disp_in) -> None:
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.location = (0, -400)
        src = self._resolve(disp_in)
        if src is None:
            return
        if src[0] == "node":
            built = self._build(src[1], 1)
            if built is not None:
                nt.links.new(built[1], disp.inputs["Height"])
        else:
            self._set_socket_value(disp.inputs["Height"], src[1], disp_in.getType())
        nt.links.new(disp.outputs["Displacement"], output.inputs["Displacement"])

    # ---------------------------------------------------------------- helpers
    def _new(self, idname: str, fallback: str | None = None):
        """Create a node, falling back when the type is unavailable in this Blender version."""
        for candidate in (idname, fallback):
            if candidate is None:
                continue
            try:
                return self.node_tree.nodes.new(candidate)
            except (RuntimeError, TypeError):
                continue
        return None

    @staticmethod
    def _input_socket(bl_node, target):
        """Resolve a socket by index, name, or list of candidate names; None if absent."""
        if isinstance(target, int):
            return bl_node.inputs[target] if 0 <= target < len(bl_node.inputs) else None
        names = (target,) if isinstance(target, str) else tuple(target)
        for name in names:
            if name in bl_node.inputs:
                return bl_node.inputs[name]
        return None

    @staticmethod
    def _first_output(bl_node, candidates: list[str]):
        for name in candidates:
            if name in bl_node.outputs:
                return bl_node.outputs[name]
        return bl_node.outputs[0] if len(bl_node.outputs) else None

    def _resolve(self, inp):
        """Resolve an input to ('node', node, output_name) or ('value', pyvalue, type) or None."""
        if inp is None:
            return None
        try:
            node = inp.getConnectedNode()
        except Exception:  # noqa: BLE001
            node = None
        if node is not None:
            out_name = inp.getOutputString() or None
            return ("node", node, out_name)
        val = inp.getValue()
        if val is not None:
            return ("value", val, inp.getType())
        return None

    @staticmethod
    def _find_socket(sockets, candidates: list[str]):
        for name in candidates:
            if name in sockets:
                return sockets[name]
        return None

    @staticmethod
    def _pick_output(bl_node, out_name: str | None):
        if not out_name:
            return None
        # MaterialX separate outputs (outr/outg/outb) -> Blender Red/Green/Blue.
        alias = {"outr": "Red", "outg": "Green", "outb": "Blue", "out": None}.get(out_name, out_name)
        if alias and alias in bl_node.outputs:
            return bl_node.outputs[alias]
        return None

    def _place(self, depth: int):
        y = self._depth_cursor.get(depth, 0.0)
        self._depth_cursor[depth] = y - 260.0
        return (-320.0 * depth, y)

    def _set_socket_value(self, socket, value, type_str: str) -> None:
        try:
            comps = self._to_components(value, type_str)
        except Exception:  # noqa: BLE001
            return
        if comps is None:
            return
        default = getattr(socket, "default_value", None)
        try:
            length = len(default)  # type: ignore[arg-type]
        except TypeError:
            length = 1
        if length == 1:
            socket.default_value = float(comps[0])
        elif length == 4:
            rgba = list(comps[:4])
            while len(rgba) < 3:
                rgba.append(rgba[-1] if rgba else 0.0)
            if len(rgba) == 3:
                rgba.append(1.0)
            socket.default_value = rgba[:4]
        else:
            vals = list(comps[:length])
            while len(vals) < length:
                vals.append(0.0)
            socket.default_value = vals

    @staticmethod
    def _to_components(value, type_str: str) -> list[float] | None:
        if type_str in ("float", "integer"):
            return [float(value)]
        if type_str == "boolean":
            return [1.0 if value else 0.0]
        # color3/color4/vector2/vector3/vector4 expose indexable components.
        try:
            return [float(value[i]) for i in range(len(value))]
        except (TypeError, ValueError):
            try:
                return [float(value)]
            except (TypeError, ValueError):
                return None

    def _load_image(self, bl_node, path: str, node) -> None:
        if not path:
            return
        resolved = path
        if not os.path.isabs(resolved):
            resolved = os.path.normpath(os.path.join(os.path.dirname(self.filepath), path))
        try:
            img = bpy.data.images.load(resolved, check_existing=True)
            bl_node.image = img
        except (RuntimeError, OSError):
            self.unsupported.append(
                {"name": node.getName(), "category": "image", "reason": f"texture not found: {path}"},
            )
            return
        # Non-color data for float/vector/normal images.
        node_type = node.getType()
        colorspace_in = node.getInput("colorspace")
        colorspace = colorspace_in.getValueString() if colorspace_in is not None else ""
        is_color = node_type in ("color3", "color4")
        if not is_color or (colorspace and "srgb" not in colorspace.lower()):
            try:
                bl_node.image.colorspace_settings.name = "Non-Color"
            except (TypeError, KeyError):
                pass


def import_materialx_to_blender(filepath: str, logger, options: dict | None = None) -> dict[str, Any]:
    """Import a MaterialX file, creating one Blender material per surface material.

    Args:
        filepath: Path to the .mtlx file.
        logger: A logging.Logger for progress/errors.
        options: Reserved for future options.

    Returns:
        A result dict with keys: success, materials, unsupported_nodes (and error on failure).
    """
    try:
        importer = MaterialXImporter(filepath, logger, options)
        result = importer.run()
    except Exception as exc:
        logger.exception("MaterialX import failed")
        return {"success": False, "error": str(exc), "materials": [], "unsupported_nodes": []}
    else:
        if result.get("unsupported_nodes"):
            logger.warning("Import finished with %s unsupported node(s)", len(result["unsupported_nodes"]))
        return result
