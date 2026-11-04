"""
MCP/tools/gui_tools.py — Native In-Process GUI Renderer Control Tools
"""

from typing import Dict, Any, Optional, List
from ..core.decorators import mcp_tool
from FILES.gui_controller import (
    launch_gui,
    add_window,
    remove_window,
    update_window_args,
    get_window_status,
    clean_all_subwindows,
    set_gui_state
)


@mcp_tool(
    name="gui_create_window",
    description="Create or register a dynamic GUI window (e.g. video player, content viewer) by name with width and height.",
    category="gui"
)
def gui_create_window(
    name: str,
    width: int = 800,
    height: int = 600,
    win_type: str = "video",
    data: str = "",
    extra_args: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Spawns or registers dynamic window in the IGUIRS presentation system."""
    try:
        if not name:
            return {"error": "Window name is required."}

        # Ensure background GUI process is active
        launch_gui()

        w = max(200, int(width))
        h = max(150, int(height))
        base_args = [f"--width={w}", f"--height={h}"]
        if extra_args:
            base_args.extend([
                a for a in extra_args
                if isinstance(a, str) and not a.startswith("--width=") and not a.startswith("--height=")
            ])

        add_window(win_id=name, win_type=win_type, data=data, extra_args=base_args)

        return {
            "status": f"Window '{name}' created ({w}x{h}, type: {win_type}).",
            "name": name,
            "width": w,
            "height": h,
            "type": win_type,
            "data": data,
            "keep_ui": True
        }
    except Exception as e:
        return {"error": f"Failed to create window '{name}': {e}"}


@mcp_tool(
    name="gui_check_window_status",
    description="Check status and telemetry of a GUI window by name (returns x, y, width, height, fps).",
    category="gui"
)
def gui_check_window_status(name: str) -> Dict[str, Any]:
    """Retrieves live coordinates, dimensions, fps, and state for a window."""
    try:
        if not name:
            return {"error": "Window name is required."}

        status = get_window_status(name)
        return {
            "status": f"Window '{name}' is {status.get('status', 'unknown')}: {status.get('width', 0)}x{status.get('height', 0)} at ({status.get('x', 0)}, {status.get('y', 0)}), {status.get('fps', 0)} FPS.",
            "window": status
        }
    except Exception as e:
        return {"error": f"Failed to check window status for '{name}': {e}"}


@mcp_tool(
    name="gui_close_window",
    description="Close a dynamic GUI window by name.",
    category="gui"
)
def gui_close_window(name: str) -> Dict[str, Any]:
    """Terminates and removes a dynamic window."""
    try:
        if not name:
            return {"error": "Window name is required."}

        remove_window(name)
        return {"status": f"Window '{name}' closed, sir.", "name": name}
    except Exception as e:
        return {"error": f"Failed to close window '{name}': {e}"}


@mcp_tool(
    name="gui_clean_window",
    description="Clean and remove dynamic GUI window(s) by name, or clean all secondary windows if name is 'all'.",
    category="gui"
)
def gui_clean_window(name: str = "") -> Dict[str, Any]:
    """Clean specific or all secondary dynamic windows."""
    try:
        clean_target = name.strip()
        if not clean_target or clean_target.lower() in ("all", "*", "secondary"):
            removed = clean_all_subwindows()
            count = len(removed)
            return {
                "status": f"Cleaned {count} secondary window(s), sir." if count else "No active secondary windows to clean, sir.",
                "cleaned_windows": removed
            }
        else:
            remove_window(clean_target)
            return {"status": f"Cleaned window '{clean_target}', sir.", "name": clean_target}
    except Exception as e:
        return {"error": f"Failed to clean window '{name}': {e}"}


@mcp_tool(
    name="gui_update_dimension",
    description="Update dimensions (width and height) of a dynamic GUI window by name.",
    category="gui"
)
def gui_update_dimension(name: str, new_width: int, new_height: int) -> Dict[str, Any]:
    """Resizes dynamic window via config."""
    try:
        if not name:
            return {"error": "Window name is required."}

        w = max(200, int(new_width))
        h = max(150, int(new_height))
        extra_args = [f"--width={w}", f"--height={h}"]

        update_window_args(name, extra_args)

        return {
            "status": f"Window '{name}' dimensions updated to {w}x{h}, sir.",
            "name": name,
            "width": w,
            "height": h
        }
    except Exception as e:
        return {"error": f"Failed to update dimensions for '{name}': {e}"}
