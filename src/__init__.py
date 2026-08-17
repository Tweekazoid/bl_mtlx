"""MaterialX Import/Export Addon for Blender"""

import json
import logging

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator, Panel

from . import blender_materialx_exporter, materialx_importer

NAME = "MaterialX Import/Export"
VERSION = "1.1.4"

bl_info = {
    "name": NAME,
    "author": "Michal Hons (info@mehpixel.com)",
    "website": "https://github.com/Tweekazoid/bl_mtlx",
    "support": "COMMUNITY",
    "version": tuple(map(int, VERSION.split("."))),  # Updated version number
    "blender": (4, 0, 0),
    "location": "Properties > Material",
    "description": "Import and export Blender materials to/from MaterialX format",
    "category": "Material",
}

MATERIALX_VERSION = "1.39"


logger = logging.getLogger(NAME)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


def print_startup_message():
    """Print startup message when addon is loaded"""
    logger.info("=" * 60)
    logger.info("🎨 %s v%s loaded successfully!", NAME, VERSION)
    logger.info("=" * 60)
    logger.info("📁 Location: Properties > Material > MaterialX")
    logger.info("🔧 Features:")
    logger.info("   • Export individual materials to MaterialX format")
    logger.info("   • Export all materials at once")
    logger.info("   • Import MaterialX files back into Blender node graphs")
    logger.info("   • Support for texture export and copying")
    logger.info("   • MaterialX 1.39 specification compliance")
    logger.info("   • Fixed mix node parameters (fg, bg, mix)")
    logger.info("   • Added layer, add, multiply nodes")
    logger.info("   • Added roughness_anisotropy and artistic_ior utilities")
    logger.info("=" * 60)
    logger.info("💡 Usage: Select a material and click 'Export MaterialX'")
    logger.info("🌐 More info: https://github.com/Tweekazoid/bl_mtlx")
    logger.info("=" * 60)


class MATERIALX_OT_export(Operator):
    """Export MaterialX file"""

    bl_idname = "materialx.export"
    bl_label = "Export MaterialX"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(
        name="File Path",
        description="Filepath used for exporting MaterialX file",
        maxlen=1024,
        subtype="FILE_PATH",
    )  # type: ignore

    filter_glob: StringProperty(
        default="*.mtlx",
        options={"HIDDEN"},
    )  # type: ignore

    export_textures: BoolProperty(
        name="Export Textures",
        description="Export texture files along with the MaterialX file",
        default=True,
    )  # type: ignore

    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture files to the export directory",
        default=True,
    )  # type: ignore

    texture_folder_name: StringProperty(
        name="Folder Name",
        description="Subfolder next to the .mtlx to copy textures into. Leave empty to copy next to the .mtlx",
        default="textures",
    )  # type: ignore

    relative_paths: BoolProperty(
        name="Relative Paths",
        description="Use relative paths for texture references",
        default=True,
    )  # type: ignore

    def execute(self, context):
        logger.info("=" * 60)
        logger.info("MATERIALX EXPORT: Starting export process")
        logger.info("=" * 60)

        if not context.material:
            logger.error("No material selected")
            self.report({"ERROR"}, "No material selected")
            return {"CANCELLED"}

        try:
            # Enhanced export with better error handling

            # Configure export options
            options = {
                "export_textures": self.export_textures,
                "copy_textures": self.copy_textures,
                "texture_folder_name": self.texture_folder_name,
                "relative_paths": self.relative_paths,
                "optimize_document": context.scene.materialx_optimize_document,
                "advanced_validation": context.scene.materialx_advanced_validation,
                "performance_monitoring": True,  # Always enabled
                "strict_mode": context.scene.materialx_strict_mode,
            }

            result = blender_materialx_exporter.export_material_to_materialx(
                context.material,
                self.filepath,
                logger,
                options,
            )

            if result["success"]:
                # Success with detailed information
                message = f"Successfully exported '{context.material.name}' to MaterialX"

                # Add performance info if available
                if result.get("performance_stats"):
                    stats = result["performance_stats"]
                    if "total_time" in stats:
                        message += f" (took {stats['total_time']:.2f}s)"

                # Add validation info if available
                if result.get("validation_results"):
                    validation = result["validation_results"]
                    if validation.get("warnings"):
                        message += f" with {len(validation['warnings'])} warnings"

                self.report({"INFO"}, message)
                logger.info("✓ Export successful: %s", message)  # Store result for UI display
                context.scene.materialx_last_export_result = json.dumps(result)

                # Show warnings in UI if any
                if "validation_results" in result and result["validation_results"].get("warnings"):
                    for warning in result["validation_results"]["warnings"][:3]:  # Show first 3 warnings
                        self.report({"WARNING"}, f"Warning: {warning}")

                return {"FINISHED"}
            # Handle export failure with specific error information
            error_message = "Export failed"

            if result.get("error"):
                error_message = result["error"]
            elif result.get("unsupported_nodes"):
                unsupported = result["unsupported_nodes"]
                if len(unsupported) == 1:
                    error_message = f"Unsupported node: {unsupported[0]['type']}"
                else:
                    error_message = f"Unsupported nodes: {len(unsupported)} nodes not supported"

            self.report({"ERROR"}, error_message)
            logger.error("✗ Export failed: %s", error_message)  # Store result for UI display

            context.scene.materialx_last_export_result = json.dumps(result)

            return {"CANCELLED"}

        except Exception as e:
            # Enhanced exception handling with specific error types
            error_message = str(e)

            # Check if it's a MaterialX-specific error
            if hasattr(e, "error_type") and hasattr(e, "get_user_friendly_message"):
                error_message = e.get_user_friendly_message()  # type: ignore
                error_type = e.error_type  # type: ignore

                # Provide specific guidance based on error type
                if error_type == "library_loading":
                    self.report({"ERROR"}, f"{error_message} Please ensure MaterialX is properly installed.")
                elif error_type == "unsupported_node":
                    self.report({"ERROR"}, f"{error_message} Consider using supported node types.")
                elif error_type == "validation_error":
                    self.report({"ERROR"}, f"{error_message} Check your material node setup.")
                else:
                    self.report({"ERROR"}, error_message)
            else:
                # Generic error handling
                self.report({"ERROR"}, f"Export failed: {error_message}")

            logger.exception("✗ Export exception: %s", error_message)
            return {"CANCELLED"}

    def invoke(self, context, event):  # noqa: ARG002
        logger.info("MATERIALX EXPORT: Invoke called - opening file dialog")

        if not context.material:
            logger.error("ERROR: No material selected during invoke")
            self.report({"ERROR"}, "No material selected")
            return {"CANCELLED"}

        logger.info("Material for file dialog: %s", context.material.name)

        # Set default filename based on material name
        default_filename = f"{context.material.name}.mtlx"
        self.filepath = default_filename
        logger.info("Default filepath set to: %s", self.filepath)

        logger.info("Opening file dialog...")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MATERIALX_OT_export_all(Operator):
    """Export all materials to MaterialX files"""

    bl_idname = "materialx.export_all"
    bl_label = "Export All Materials"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(
        name="Directory",
        description="Directory to export MaterialX files",
        maxlen=1024,
        subtype="DIR_PATH",
    )  # type: ignore

    export_textures: BoolProperty(
        name="Export Textures",
        description="Export texture files along with the MaterialX files",
        default=True,
    )  # type: ignore

    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture files to the export directory",
        default=True,
    )  # type: ignore

    texture_folder_name: StringProperty(
        name="Folder Name",
        description="Subfolder next to the .mtlx to copy textures into. Leave empty to copy next to the .mtlx",
        default="textures",
    )  # type: ignore

    relative_paths: BoolProperty(
        name="Relative Paths",
        description="Use relative paths for texture references",
        default=True,
    )  # type: ignore

    def execute(self, context):
        if not self.directory:
            self.report({"ERROR"}, "No directory selected")
            return {"CANCELLED"}

        # Export options
        options = {
            "export_textures": self.export_textures,
            "copy_textures": self.copy_textures,
            "texture_folder_name": self.texture_folder_name,
            "relative_paths": self.relative_paths,
            "materialx_version": MATERIALX_VERSION,
            "optimize_document": context.scene.materialx_optimize_document,
            "advanced_validation": context.scene.materialx_advanced_validation,
            "performance_monitoring": True,  # Always enabled
            "strict_mode": context.scene.materialx_strict_mode,
        }

        logger.info("Export options: %s", options)
        logger.info("Directory: %s", self.directory)
        logger.info("Export textures: %s", self.export_textures)
        logger.info("Copy textures: %s", self.copy_textures)
        logger.info("Relative paths: %s", self.relative_paths)

        # Export all materials
        results = blender_materialx_exporter.export_all_materials_to_materialx(self.directory, logger, options)
        logger.info("Results: %s", results)

        # Report results
        successful = sum(1 for success in results.values() if success)
        total = len(results)

        # Store result for UI display

        result_data = {
            "success": successful == total,
            "total_materials": total,
            "successful_exports": successful,
            "failed_exports": total - successful,
            "results": results,
        }
        context.scene.materialx_last_export_result = json.dumps(result_data)

        if successful == total:
            self.report({"INFO"}, f"Successfully exported all {total} materials")
        else:
            failed = total - successful
            self.report({"WARNING"}, f"Exported {successful}/{total} materials ({failed} failed)")

        return {"FINISHED"}

    def invoke(self, context, event):  # noqa: ARG002
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MATERIALX_OT_import(Operator):
    """Import a MaterialX file as a new Blender material"""

    bl_idname = "materialx.import_file"
    bl_label = "Import MaterialX"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(
        name="File Path",
        description="Filepath of the MaterialX file to import",
        maxlen=1024,
        subtype="FILE_PATH",
    )  # type: ignore

    filter_glob: StringProperty(
        default="*.mtlx",
        options={"HIDDEN"},
    )  # type: ignore

    assign_to_object: BoolProperty(
        name="Assign to Active Object",
        description="Assign the first imported material to the active object",
        default=True,
    )  # type: ignore

    def execute(self, context):
        logger.info("=" * 60)
        logger.info("MATERIALX IMPORT: Starting import of %s", self.filepath)
        logger.info("=" * 60)

        if not self.filepath:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}

        try:
            result = materialx_importer.import_materialx_to_blender(self.filepath, logger)
        except Exception as exc:
            logger.exception("MaterialX import raised an exception")
            self.report({"ERROR"}, f"Import failed: {exc}")
            return {"CANCELLED"}

        if not result.get("success"):
            error_message = result.get("error", "Import failed")
            self.report({"ERROR"}, error_message)
            logger.error("✗ Import failed: %s", error_message)
            return {"CANCELLED"}

        materials = result.get("materials", [])
        unsupported = result.get("unsupported_nodes", [])

        # Optionally assign the first imported material to the active object.
        if self.assign_to_object and materials:
            obj = context.active_object
            first_mat = bpy.data.materials.get(materials[0])
            if obj is not None and first_mat is not None and hasattr(obj.data, "materials"):
                if obj.data.materials:
                    obj.data.materials[0] = first_mat
                else:
                    obj.data.materials.append(first_mat)

        message = f"Imported {len(materials)} material(s)"
        if unsupported:
            message += f" with {len(unsupported)} unsupported node(s)"
            for item in unsupported[:5]:
                self.report({"WARNING"}, f"Unsupported: {item['category']} ({item['reason']})")
        self.report({"INFO"}, message)
        logger.info("✓ Import successful: %s", message)
        context.scene.materialx_last_import_result = json.dumps(result)
        return {"FINISHED"}

    def invoke(self, context, event):  # noqa: ARG002
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MATERIALX_PT_panel(Panel):
    """MaterialX panel in Properties > Material"""

    bl_label = "MaterialX"
    bl_idname = "MATERIALX_PT_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    def draw(self, context):
        layout = self.layout

        if not context.material:
            layout.label(text="No material selected")
            return

        # Main export section
        box = layout.box()
        box.label(text="Export MaterialX", icon="EXPORT")

        col = box.column(align=True)
        col.operator("materialx.export", text="Export MaterialX", icon="EXPORT")

        # Import section
        box = layout.box()
        box.label(text="Import MaterialX", icon="IMPORT")

        col = box.column(align=True)
        col.operator("materialx.import_file", text="Import MaterialX", icon="IMPORT")

        # Export all materials section
        box = layout.box()
        box.label(text="Export All Materials", icon="MATERIAL")

        col = box.column(align=True)
        col.operator("materialx.export_all", text="Export All Materials", icon="MATERIAL")

        # Configuration section
        box = layout.box()
        box.label(text="Configuration", icon="SETTINGS")

        # Get current configuration - use individual properties instead of a dict
        # This avoids the UI context writing issue

        col = box.column(align=True)

        # Core settings
        col.prop(context.scene, "materialx_optimize_document", text="Optimize Document")
        col.prop(context.scene, "materialx_advanced_validation", text="Validation")

        # Error handling
        col.separator()
        col.prop(context.scene, "materialx_strict_mode", text="Strict Mode (Fail on Unsupported Features)")

        # Status information
        if hasattr(context.scene, "materialx_last_export_result"):
            result_str = context.scene.materialx_last_export_result
            if result_str:
                try:
                    result = json.loads(result_str)

                    box = layout.box()
                    box.label(text="Last Export Status", icon="INFO")

                    if result.get("success"):
                        col = box.column(align=True)
                        col.label(text="✓ Export Successful", icon="CHECKMARK")

                        # Handle single material export results
                        if "performance_stats" in result:
                            stats = result["performance_stats"]
                            if "total_time" in stats:
                                col.label(text=f"Time: {stats['total_time']:.2f}s")

                        if "validation_results" in result:
                            validation = result["validation_results"]
                            if validation.get("warnings"):
                                col.label(text=f"Warnings: {len(validation['warnings'])}", icon="ERROR")

                        # Handle export all results
                        if "total_materials" in result:
                            col.label(
                                text=f"Materials: {result['successful_exports']}/{result['total_materials']} exported",
                            )
                    else:
                        col = box.column(align=True)
                        col.label(text="✗ Export Failed", icon="ERROR")

                        if "error" in result:
                            col.label(text=f"Error: {result['error']}")

                        if result.get("unsupported_nodes"):
                            unsupported = result["unsupported_nodes"]
                            col.label(text=f"Unsupported: {len(unsupported)} nodes")

                        # Handle export all failure results
                        if "failed_exports" in result:
                            col.label(text=f"Failed: {result['failed_exports']}/{result['total_materials']} materials")
                except (json.JSONDecodeError, KeyError):
                    # If JSON parsing fails, just show the raw string
                    box = layout.box()
                    box.label(text="Last Export Status", icon="INFO")
                    col = box.column(align=True)
                    col.label(text=f"Status: {result_str}")


# Add properties to scene for configuration
def register_properties():
    bpy.types.Scene.materialx_optimize_document = BoolProperty(
        name="Optimize",
        description="Optimize MaterialX document by removing unused nodes",
        default=True,
    )

    bpy.types.Scene.materialx_advanced_validation = BoolProperty(
        name="Validation",
        description="Enable comprehensive MaterialX document validation",
        default=True,
    )

    bpy.types.Scene.materialx_strict_mode = BoolProperty(
        name="Strict Mode (Fail on Unsupported Features)",
        description="Fail export on any unsupported features or errors",
        default=True,
    )

    # Store export result as a JSON string to preserve structure
    bpy.types.Scene.materialx_last_export_result = bpy.props.StringProperty(
        name="Last Export Result",
        description="Result of the last MaterialX export operation",
        default="",
    )

    # Store import result as a JSON string to preserve structure
    bpy.types.Scene.materialx_last_import_result = bpy.props.StringProperty(
        name="Last Import Result",
        description="Result of the last MaterialX import operation",
        default="",
    )


def unregister_properties():
    del bpy.types.Scene.materialx_optimize_document
    del bpy.types.Scene.materialx_advanced_validation
    del bpy.types.Scene.materialx_strict_mode
    del bpy.types.Scene.materialx_last_export_result
    del bpy.types.Scene.materialx_last_import_result


classes = (
    MATERIALX_OT_export,
    MATERIALX_OT_export_all,
    MATERIALX_OT_import,
    MATERIALX_PT_panel,
)


def menu_func_import(self, context):  # noqa: ARG001
    """Add MaterialX import entry to the File > Import menu."""
    self.layout.operator(MATERIALX_OT_import.bl_idname, text="MaterialX (.mtlx)")


def menu_func_export(self, context):  # noqa: ARG001
    """Add MaterialX export entry to the File > Export menu."""
    self.layout.operator(MATERIALX_OT_export.bl_idname, text="MaterialX (.mtlx)")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    # Print startup message
    print_startup_message()

    # Register properties
    register_properties()


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Print unload message
    logger.info("🎨 %s v%s unloaded", NAME, VERSION)  # Unregister properties
    unregister_properties()


if __name__ == "__main__":
    register()
