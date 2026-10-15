"""Compatibility entrypoint for Aminate shelf buttons installed before renaming."""


def launch_maya_anim_workflow_tools(dock=True, initial_tab="quick_start"):
    """Open the current retained Aminate UI without reloading its modules."""
    import aminate

    return aminate.launch_aminate(dock=True, initial_tab=initial_tab)
