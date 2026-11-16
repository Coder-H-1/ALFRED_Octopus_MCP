"""
MCP/tools/system_tools.py — Native In-Process System Management Tools
"""

import os
import subprocess
import webbrowser
import keyboard
from typing import Dict, Any, Optional
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ..core.decorators import mcp_tool

PROTECTED_PROCESSES = {
    "explorer.exe", "lsass.exe", "csrss.exe", "smss.exe", "services.exe",
    "svchost.exe", "wininit.exe", "winlogon.exe", "system", "idle"
}

APP_MAP = {
    # System & utilities
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "cmd": "start cmd",
    "command prompt": "start cmd",
    "terminal": "start powershell",
    "powershell": "start powershell",
    "system information": "start dxdiag",
    "dxdiag": "start dxdiag",
    "task manager": "start taskmgr",
    "taskmanager": "start taskmgr",
    "task mgr": "start taskmgr",
    "resource monitor": "start resmon",
    "resmon": "start resmon",
    "advanced system settings": "start sysdm.cpl",
    "advance settings": "start sysdm.cpl",
    "system properties": "start sysdm.cpl",
    "settings": "start ms-settings:",
    "computer settings": "start ms-settings:",
    "minecraft": "start %Appdata%/.minecraft/TLauncher.exe",

    # Browsers
    "browser": "start chrome",
    "chrome": "start chrome",
    "incognito chrome": "start chrome --incognito",
    "firefox": "start firefox.exe",

    # IDEs / Dev tools
    "code": f'antigravity-ide.exe "{os.getcwd()}"',
    "antigravity": f'antigravity-ide.exe "{os.getcwd()}"',
    "antigravity ide": f'antigravity-ide.exe "{os.getcwd()}"',

    # Web services
    "google": "start chrome https://www.google.com",
    "search": "start chrome https://www.google.com",
    "youtube": "start chrome https://youtube.com",
    "youtube music": "start chrome https://music.youtube.com",
    "github": "start chrome https://github.com",
    "gemini": "start chrome https://gemini.google.com",
    "chatgpt": "start chrome https://chatgpt.com",
    "stackoverflow": "start chrome https://www.stackoverflow.com",
    "amazon": "start chrome https://amazon.in",
    "flipkart": "start chrome https://flipkart.com",
    "instagram": "start chrome https://instagram.com",
    "whatsapp": "start chrome https://web.whatsapp.com",
    "facebook": "start chrome https://facebook.com",
    "twitter": "start chrome https://twitter.com",
    "linkedin": "start chrome https://linkedin.com",
}

CLOSE_PROCESS_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "browser": "chrome.exe",
    "firefox": "firefox.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "powershell.exe",
    "powershell": "powershell.exe",
    "system information": "dxdiag.exe",
    "dxdiag": "dxdiag.exe",
    "code": "antigravity-ide.exe",
    "antigravity": "antigravity-ide.exe",
    "antigravity ide": "antigravity-ide.exe",
    "task manager": "taskmgr.exe",
    "taskmanager": "taskmgr.exe",
    "resource monitor": "resmon.exe",
    "resmon": "resmon.exe",
    "minecraft": "TLauncher.exe",
}

_volume_interface = None

def _get_volume_interface():
    global _volume_interface
    if not _volume_interface:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
    return _volume_interface


@mcp_tool(
    name="system_set_volume",
    description="Set system audio volume level to an exact percentage from 0 to 100.",
    category="system"
)
def set_volume(level: int) -> Dict[str, Any]:
    """Sets master volume on Windows host."""
    level = max(0, min(100, int(level)))
    try:
        vol = _get_volume_interface()
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"level": level, "status": f"Volume set to {level}%, sir."}
    except Exception as e:
        return {"error": f"Failed to set volume: {e}"}


@mcp_tool(
    name="system_adjust_volume",
    description="Adjust system audio volume up or down relatively. Direction can be 'increase' or 'decrease'.",
    category="system"
)
def adjust_volume(direction: str = "increase", amount: int = 10) -> Dict[str, Any]:
    """Increases or decreases master volume."""
    try:
        vol = _get_volume_interface()
        current = vol.GetMasterVolumeLevelScalar() * 100
        delta = amount if direction.lower() in ["increase", "up", "raise", "higher"] else -amount
        target = max(0, min(100, int(round(current + delta))))
        vol.SetMasterVolumeLevelScalar(target / 100.0, None)
        return {"level": target, "status": f"Volume set to {target}%, sir."}
    except Exception as e:
        return {"error": f"Failed to adjust volume: {e}"}


@mcp_tool(
    name="system_mute_volume",
    description="Toggle or enable mute on system audio volume.",
    category="system"
)
def mute_volume(mute_state: Optional[bool] = None) -> Dict[str, Any]:
    """Mutes or unmutes master audio."""
    try:
        vol = _get_volume_interface()
        if mute_state is None:
            current_mute = vol.GetMute()
            new_mute = 0 if current_mute else 1
        else:
            new_mute = 1 if mute_state else 0
        vol.SetMute(new_mute, None)
        msg = "Audio muted, sir." if new_mute else "Audio unmuted, sir."
        return {"muted": bool(new_mute), "status": msg}
    except Exception as e:
        return {"error": f"Failed to toggle mute: {e}"}


@mcp_tool(
    name="app_open",
    description="Launch desktop applications or websites on the host computer.",
    category="system"
)
def open_app(app_name: str) -> Dict[str, Any]:
    """Launches application executable or mapped shortcut."""
    clean_name = app_name.lower().strip()
    if any(char in clean_name for char in (";", "&", "|", "<", ">", "`", "%")):
        return {"error": "Invalid characters in application name."}

    if clean_name in APP_MAP:
        cmd = APP_MAP[clean_name]
    else:
        # Proper Windows start syntax to handle space-separated app names or custom commands
        cmd = f'start "" "{clean_name}"'
    try:
        subprocess.Popen(cmd, shell=True)
        return {"status": f"Launched {app_name}, sir."}
    except Exception as e:
        return {"error": f"Failed to launch {app_name}: {e}"}


@mcp_tool(
    name="app_close",
    description="Close or terminate a running application by name.",
    category="system"
)
def close_app(app_name: str) -> Dict[str, Any]:
    """Closes process corresponding to app name."""
    clean_name = app_name.lower().strip()
    proc_name = CLOSE_PROCESS_MAP.get(clean_name, clean_name if clean_name.endswith(".exe") else f"{clean_name}.exe")
    if proc_name.lower() in PROTECTED_PROCESSES:
        return {"error": f"Refusing to terminate critical system process '{proc_name}'."}
    try:
        subprocess.Popen(f"taskkill /f /im {proc_name}", shell=True)
        return {"status": f"Closed {app_name}, sir."}
    except Exception as e:
        return {"error": f"Failed to close {app_name}: {e}"}


@mcp_tool(
    name="workspace_open",
    description="Open development workspace environment with Gemini and Antigravity IDE.",
    category="system"
)
def open_workspace() -> Dict[str, Any]:
    """Launches Gemini web interface and Antigravity IDE."""
    try:
        webbrowser.open_new_tab("https://gemini.google.com/")
        subprocess.Popen(f'antigravity-ide "{os.getcwd()}"', shell=True)
        return {"status": "Opening Workspace, sir."}
    except Exception as e:
        return {"error": f"Failed to open workspace: {e}"}


@mcp_tool(
    name="workspace_close",
    description="Close development workspace environment.",
    category="system"
)
def close_workspace() -> Dict[str, Any]:
    """Closes Antigravity IDE."""
    try:
        subprocess.Popen("taskkill /f /im antigravity-ide.exe", shell=True)
        return {"status": "Closed Workspace, sir."}
    except Exception as e:
        return {"error": f"Failed to close workspace: {e}"}


@mcp_tool(
    name="desktop_show",
    description="Show desktop by minimizing or toggling windows.",
    category="system"
)
def show_desktop() -> Dict[str, Any]:
    """Toggles desktop view using Windows shortcut."""
    try:
        keyboard.press_and_release("win + d")
        return {"status": "Showing desktop now, sir."}
    except Exception as e:
        return {"error": f"Failed to show desktop: {e}"}
