"""Keep generated BLEND outliners minimal and unambiguous.

The source-partition exporter intentionally creates one Blender mesh object per
source MESH record. Blender's glTF importer also parents these objects to the
armature and leaves them linked to its import collection. Linking them again to
``__MESH_PARTS`` therefore makes the same objects appear in several Outliner
locations. SKEL helper nodes are useful as metadata, but visible helper empties
and duplicate non-deforming bones add further clutter.

This patch keeps exactly:

* one armature object with its imported skin bones;
* one ``__MESH_PARTS`` collection containing all source MESH objects.

Mesh objects retain their Armature modifiers and world transforms, but are not
parented to the armature. Visible SKEL helper nodes are disabled; their decoded
information remains available in the raw skeleton reports/manifests.
"""
from __future__ import annotations

import mesh_partition_export_patch
import skeletal_tail_patch


def _skip_visible_skel_helpers(glb_path, skeleton):
    """Do not add non-skin SKEL nodes to the exported GLB scene."""
    return []


def _minimal_blend_script(glb_path, blend_path, obj_path=None) -> str:
    """Append a deterministic Outliner cleanup pass to the partition script."""
    script = mesh_partition_export_patch._blend_script(glb_path, blend_path, obj_path)
    cleanup = [
        "# PAKPY minimal Outliner cleanup",
        "part_collection=bpy.data.collections.get(entry_name+'__MESH_PARTS')",
        "mesh_parts=[obj for obj in list(bpy.context.scene.objects) if obj.type=='MESH' and bool(obj.get('pakpy_source_mesh_partition'))]",
        "for obj in mesh_parts:",
        "    world=obj.matrix_world.copy()",
        "    obj.parent=None",
        "    obj.matrix_world=world",
        "    if part_collection is not None and obj.name not in part_collection.objects: part_collection.objects.link(obj)",
        "    for collection in list(obj.users_collection):",
        "        if part_collection is None or collection!=part_collection: collection.objects.unlink(obj)",
        "helper_objects=[obj for obj in list(bpy.data.objects) if bool(obj.get('pakpy_skel_helper')) or bool(obj.get('pakpy_non_deform_helper'))]",
        "for obj in helper_objects: bpy.data.objects.remove(obj,do_unlink=True)",
        "removed_helper_bones=0",
        "if armature_obj is not None:",
        "    helper_bone_names=[bone.name for bone in armature_obj.data.bones if bool(bone.get('pakpy_skel_helper')) or bool(bone.get('pakpy_non_deform_helper'))]",
        "    if helper_bone_names:",
        "        try:",
        "            bpy.ops.object.select_all(action='DESELECT')",
        "            armature_obj.select_set(True)",
        "            bpy.context.view_layer.objects.active=armature_obj",
        "            bpy.ops.object.mode_set(mode='EDIT')",
        "            for name in helper_bone_names:",
        "                bone=armature_obj.data.edit_bones.get(name)",
        "                if bone is not None: armature_obj.data.edit_bones.remove(bone); removed_helper_bones+=1",
        "            bpy.ops.object.mode_set(mode='OBJECT')",
        "        except Exception as exc:",
        "            try: bpy.ops.object.mode_set(mode='OBJECT')",
        "            except Exception: pass",
        "            armature_obj['pakpy_helper_cleanup_error']=str(exc)",
        "for collection in list(bpy.data.collections):",
        "    if collection.name==entry_name+'__SKEL_HELPERS' or collection.name.endswith('__SKEL_HELPERS'):",
        "        bpy.data.collections.remove(collection)",
        "Path(BLEND_PATH).parent.mkdir(parents=True,exist_ok=True)",
        "bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)",
        "print('PAKPY_OUTLINER_MESH_PARTS=%d' % len(mesh_parts))",
        "print('PAKPY_OUTLINER_REMOVED_HELPER_OBJECTS=%d' % len(helper_objects))",
        "print('PAKPY_OUTLINER_REMOVED_HELPER_BONES=%d' % removed_helper_bones)",
        "",
    ]
    return script + "\n" + "\n".join(cleanup)


def install() -> None:
    # The already-installed wrapper resolves this global at export time.
    mesh_partition_export_patch._patch_skel_helper_nodes = _skip_visible_skel_helpers
    skeletal_tail_patch._connected_blend_script = _minimal_blend_script
