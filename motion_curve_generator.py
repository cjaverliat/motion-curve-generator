import bpy
from mathutils import Vector

bl_info = {
    "name": "Motion Curve Generator",
    "blender": (4, 1, 0),
    "category": "Animation",
}


def compute_cumulative_length(points):
    total_length = 0
    n_points = len(points)
    cumulative_lengths = [0] * n_points
    for i in range(n_points - 1):
        total_length += (points[i + 1] - points[i]).length
        cumulative_lengths[i + 1] = total_length
    return cumulative_lengths, total_length


def create_curve_from_points(points, name):
    n_points = len(points)
    n_segments = n_points - 1

    # Create curve
    curve_data = bpy.data.curves.new(f"{name}_curve", "CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(n_segments)

    for i, p in enumerate(points):
        spline.bezier_points[i].co = p
        spline.bezier_points[i].handle_right_type = "AUTO"
        spline.bezier_points[i].handle_left_type = "AUTO"

    # Compute cumulative lengths
    cumulative_lengths, total_length = compute_cumulative_length(points)

    # Create curve object
    curve_obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(curve_obj)

    # Add eval_time animation
    action = bpy.data.actions.new(name=f"{name}_Animation")
    curve_data.animation_data_create()
    curve_data.animation_data.action = action

    fcurve_eval_time = action.fcurves.new("eval_time")
    fcurve_eval_time.keyframe_points.add(n_points)

    for i in range(n_points):
        progress = cumulative_lengths[i] / total_length if total_length != 0 else 0
        fcurve_eval_time.keyframe_points[i].co = (i, progress * 100)
        fcurve_eval_time.keyframe_points[i].interpolation = "LINEAR"

    return curve_obj


class OBJECT_OT_motion_to_curve(bpy.types.Operator):
    bl_idname = "object.motion_to_curve"
    bl_label = "Generate Motion Curve"
    bl_description = "Convert motion path (bone or mesh) to curve"

    bake_location: bpy.props.EnumProperty(
        name="Bake Location",
        description="Choose whether to bake head or tail of bone",
        items=[
            ("TAILS", "Tails", "Use bone tail locations"),
            ("HEADS", "Heads", "Use bone head locations"),
        ],
        default="TAILS",
    )

    def execute(self, context):
        obj = context.active_object

        if obj.type == "ARMATURE":
            selected_bone = context.active_pose_bone
            if not selected_bone:
                self.report({"ERROR"}, "No bone selected")
                return {"CANCELLED"}

            if selected_bone.motion_path is not None:
                bpy.ops.pose.paths_clear(only_selected=True)
            bpy.ops.pose.paths_calculate(
                bake_location=self.bake_location,
                range="KEYS_ALL",
            )
            motion_path = selected_bone.motion_path
            create_curve_from_points(
                [p.co.copy() for p in motion_path.points], f"{selected_bone.name}_curve"
            )
            bpy.ops.pose.paths_clear(only_selected=True)
        else:
            # Mesh case: compute vertex center per frame
            depsgraph = context.evaluated_depsgraph_get()
            frames = range(context.scene.frame_start, context.scene.frame_end + 1)
            points = []

            for frame in frames:
                context.scene.frame_set(frame)
                eval_obj = obj.evaluated_get(depsgraph)
                mesh = eval_obj.to_mesh()
                avg_co = sum((v.co for v in mesh.vertices), Vector()) / len(mesh.vertices)
                points.append(eval_obj.matrix_world @ avg_co)
                eval_obj.to_mesh_clear()

            create_curve_from_points(points, f"{obj.name}_trail")

        self.report({"INFO"}, "Motion converted to curve")
        return {"FINISHED"}

    def invoke(self, context, event):
        obj = context.active_object
        if obj.type == "ARMATURE":
            # Only prompt dialog for armatures (bake location)
            return context.window_manager.invoke_props_dialog(self)
        else:
            # Directly execute for meshes
            return self.execute(context)


def menu_func(self, context):
    self.layout.operator(OBJECT_OT_motion_to_curve.bl_idname)


def register():
    bpy.utils.register_class(OBJECT_OT_motion_to_curve)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    bpy.types.VIEW3D_MT_pose.append(menu_func)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_motion_to_curve)
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    bpy.types.VIEW3D_MT_pose.remove(menu_func)


if __name__ == "__main__":
    register()
 
