import bpy

bl_info = {
    "name": "Motion Curve Generator",
    "blender": (4, 1, 0),
    "category": "Animation",
}


def compute_motion_path_cumulative_length(motion_path):
    total_length = 0
    n_points = len(motion_path.points)
    cumulative_lengths = [0] * n_points

    for i in range(n_points - 1):
        point = motion_path.points[i].co
        next_point = motion_path.points[i + 1].co
        total_length += (next_point - point).length
        cumulative_lengths[i + 1] = total_length

    return cumulative_lengths, total_length


def create_curve_from_motion_path(motion_path, name):
    n_points = len(motion_path.points)
    n_segments = n_points - 1

    # Create path points (one per frame)
    path = bpy.data.curves.new(f"{name}_path", "CURVE")
    path.dimensions = "3D"
    spline = path.splines.new("BEZIER")
    spline.bezier_points.add(n_segments)

    for i, point in enumerate(spline.bezier_points):
        point.co = motion_path.points[i].co
        point.handle_right_type = "AUTO"
        point.handle_left_type = "AUTO"

    # Create the animation, change speed depending on segment lengths
    cumulative_lengths, total_length = compute_motion_path_cumulative_length(
        motion_path
    )

    curve = bpy.data.objects.new(name, path)
    bpy.context.scene.collection.objects.link(curve)

    action = bpy.data.actions.new(name=f"{name}_Animation")

    eval_time_data_path = "eval_time"
    fcurve_eval_time = action.fcurves.find(eval_time_data_path)

    if fcurve_eval_time is None:
        fcurve_eval_time = action.fcurves.new(eval_time_data_path)

    fcurve_eval_time.keyframe_points.add(n_points)
    fcurve_eval_time.keyframe_points[0].co = (motion_path.frame_start, 0)
    fcurve_eval_time.keyframe_points[0].interpolation = "LINEAR"

    for segment_idx in range(n_segments):
        progress = cumulative_lengths[segment_idx] / total_length
        point_idx = segment_idx + 1
        fcurve_eval_time.keyframe_points[point_idx].co = (
            segment_idx + 1,
            progress * 100,
        )
        fcurve_eval_time.keyframe_points[point_idx].interpolation = "LINEAR"

    animation_data = path.animation_data_create()
    animation_data.action = action

    return curve


class POSE_OT_motion_path_to_curve(bpy.types.Operator):
    bl_idname = "pose.motion_path_to_curve"
    bl_label = "Generate Motion Curve"
    bl_description = "Convert motion path to curve"

    bake_location: bpy.props.EnumProperty(
        name="Bake Location",
        description="Choose whether to bake head or tail of bone",
        items=[
            ("TAILS", "Tails", "Use bone tail locations"),
            ("HEADS", "Heads", "Use bone head locations"),
        ],
        default="TAILS",
    )  # type: ignore

    def execute(self, context):
        armature = bpy.context.active_object

        if armature.type != "ARMATURE":
            self.report({"ERROR"}, "Active object is not an armature.")
            return {"CANCELLED"}

        selected_bone = bpy.context.active_pose_bone

        if selected_bone is None:
            self.report({"ERROR"}, "No bone selected.")
            return {"CANCELLED"}

        bone_name = selected_bone.name

        if selected_bone.motion_path is not None:
            bpy.ops.pose.paths_clear(only_selected=True)

        bpy.ops.pose.paths_calculate(
            bake_location=self.bake_location,
            range="KEYS_ALL",
        )
        motion_path = selected_bone.motion_path

        create_curve_from_motion_path(motion_path, f"{bone_name}_curve")

        bpy.ops.pose.paths_clear(only_selected=True)

        self.report({"INFO"}, "Motion path converted to curve.")
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class OBJECT_OT_transfer_curve_animation(bpy.types.Operator):
    bl_idname = "object.transfer_curve_animation"
    bl_label = "Transfer Curve Animation"
    bl_description = "Transfer curve animation to target object"

    axis: bpy.props.EnumProperty(
        name="Axis",
        description="Choose which axis to animate",
        items=[
            ("POS_X", "X", "Animate X axis"),
            ("POS_Y", "Y", "Animate Y axis"),
            ("POS_Z", "Z", "Animate Z axis"),
            ("NEG_X", "-X", "Animate NEG_X axis"),
            ("NEG_Y", "-Y", "Animate NEG_Y axis"),
            ("NEG_Z", "-Z", "Animate NEG_Z axis"),
        ],
        default="POS_X",
    )  # type: ignore

    def execute(self, context):
        # Get selected objects
        selected_objects = context.selected_objects
        if len(selected_objects) != 2:
            self.report(
                {"ERROR"}, "Please select exactly 2 objects (curve and target object)"
            )
            return {"CANCELLED"}

        # Find curve and target object
        curve = None
        target_obj = None
        for obj in selected_objects:
            if obj.type == "CURVE":
                curve = obj
            else:
                target_obj = obj

        if not curve or not target_obj:
            self.report({"ERROR"}, "Please select a curve and a target object")
            return {"CANCELLED"}

        if len(curve.data.splines) != 1:
            self.report({"ERROR"}, "Expected curve to have exactly one spline")
            return {"CANCELLED"}

        curve_length = curve.data.splines[0].calc_length()

        try:
            fcurve_eval_time = curve.data.animation_data.action.fcurves.find(
                "eval_time"
            )
        except AttributeError:
            self.report({"ERROR"}, "Expected curve to have eval_time fcurve")
            return {"CANCELLED"}

        # Create animation data
        action = bpy.data.actions.new(name=f"{target_obj.name}_follow_curve_animation")
        target_obj.animation_data_create()
        target_obj.animation_data.action = action

        fcurve_location = action.fcurves.new(
            "location",
            index={
                "POS_X": 0,
                "POS_Y": 1,
                "POS_Z": 2,
                "NEG_X": 0,
                "NEG_Y": 1,
                "NEG_Z": 2,
            }[self.axis],
        )

        fcurve_location.keyframe_points.add(len(fcurve_eval_time.keyframe_points))

        for i, point in enumerate(fcurve_location.keyframe_points):
            progress = fcurve_eval_time.keyframe_points[i].co[1] / 100
            pos = progress * curve_length

            if self.axis.startswith("NEG_"):
                pos = -pos

            point.co = (i, pos)
            point.interpolation = "LINEAR"

        self.report(
            {"INFO"}, f"Added animation to {target_obj.name} along {self.axis} axis"
        )
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


def pose_menu_func(self, context):
    self.layout.operator(POSE_OT_motion_path_to_curve.bl_idname)


def object_menu_func(self, context):
    self.layout.operator(OBJECT_OT_transfer_curve_animation.bl_idname)


def register():
    bpy.utils.register_class(POSE_OT_motion_path_to_curve)
    bpy.utils.register_class(OBJECT_OT_transfer_curve_animation)
    bpy.types.VIEW3D_MT_pose.append(pose_menu_func)
    bpy.types.VIEW3D_MT_object.append(object_menu_func)


def unregister():
    bpy.utils.unregister_class(POSE_OT_motion_path_to_curve)
    bpy.utils.unregister_class(OBJECT_OT_transfer_curve_animation)
    bpy.types.VIEW3D_MT_pose.remove(pose_menu_func)
    bpy.types.VIEW3D_MT_object.remove(object_menu_func)


if __name__ == "__main__":
    print("Registering motion_curve_generator")
    register()
