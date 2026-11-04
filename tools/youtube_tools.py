"""
MCP/tools/youtube_tools.py — Native In-Process YouTube Streaming Tools
"""

from typing import Dict, Any, Optional
import re
from ..core.decorators import mcp_tool
from .gui_tools import gui_create_window, gui_close_window


@mcp_tool(
    name="youtube_play",
    description="Search and play a video or music track from YouTube by song/video name or query with optional song index and list preview.",
    category="media"
)
def youtube_play(
    query: str,
    index: int = 1,
    show_list: bool = False,
    explicit_index: bool = False
) -> Dict[str, Any]:
    """Routes YouTube playback through the GUI dynamic window MCP tool."""
    try:
        raw_query = str(query).strip()
        if not raw_query:
            return {"error": "Query cannot be empty, sir."}

        clean_lower = raw_query.lower()
        if not show_list and any(kw in clean_lower for kw in ("show list", "show options", "display list", "list options", "show results")):
            show_list = True

        target_idx = int(index)
        if target_idx <= 1 and not explicit_index:
            ord_map = {
                "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
                "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
                "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9
            }
            ord_match = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th)\b", clean_lower)
            if ord_match:
                target_idx = ord_map.get(ord_match.group(1).lower(), 1)
                explicit_index = True
            else:
                num_match = re.search(r"\b(?:song|number|track|option|item)\s*(?:no\.?|number)?\s*(\d+)\b", clean_lower)
                if num_match:
                    try:
                        target_idx = int(num_match.group(1))
                        explicit_index = True
                    except Exception:
                        target_idx = 1

        target_idx = max(1, target_idx)

        # Clean search query for yt-dlp
        clean_q = raw_query
        clean_q = re.sub(r"\b(?:and\s+)?(?:show\s+(?:the\s+)?list|show\s+options|display\s+list|list\s+options|show\s+results)\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\b(?:the\s+)?(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th)\s+(?:song|video|track|option)?\s*(?:of|from)?\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\b(?:song|number|track|option|item)\s*(?:no\.?|number)?\s*\d+\s*(?:of|from)?\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\b(?:on|from|in)?\s*youtube\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"^\s*(?:song|video|track|music)\s+", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\s+", " ", clean_q).strip(" ,.-")
        if not clean_q:
            clean_q = raw_query

        title = clean_q
        extra_args = [f"--index={target_idx}"]
        if show_list:
            extra_args.append("--show-list")
        if explicit_index:
            extra_args.append("--explicit-index")

        # Spawn dynamic window via GUI MCP Tool
        win_res = gui_create_window(
            name="youtube_window",
            width=800,
            height=600,
            win_type="video",
            data=clean_q,
            extra_args=extra_args
        )

        if "error" in win_res:
            return win_res

        if show_list:
            if explicit_index:
                status_msg = f"Showing YouTube options for '{title}'. Selected #{target_idx}, sir."
            else:
                status_msg = f"Showing YouTube options for '{title}', sir."
        else:
            if target_idx > 1:
                status_msg = f"Playing option #{target_idx} for '{title}' from YouTube, sir."
            else:
                status_msg = f"Playing '{title}' from YouTube, sir."

        return {
            "status": status_msg,
            "keep_ui": True,
            "title": title,
            "index": target_idx,
            "show_list": show_list,
            "explicit_index": explicit_index,
            "window": "youtube_window"
        }

    except Exception as e:
        return {"error": f"YouTube playback failed: {e}"}


@mcp_tool(
    name="youtube_stop",
    description="Stop active YouTube video playback and close player.",
    category="media"
)
def youtube_stop() -> Dict[str, Any]:
    """Closes the YouTube dynamic player window via GUI MCP Tool."""
    try:
        res = gui_close_window(name="youtube_window")
        if "error" in res:
            return {"status": "YouTube player is not currently active, sir."}
        return {"status": "Stopped YouTube playback and closed player, sir."}
    except Exception as e:
        return {"error": f"Failed to stop playback: {e}"}



_YOUTUBE_VOLUME = 100

@mcp_tool(
    name="youtube_set_volume",
    description="Set YouTube playback volume level from 0 to 100 percent.",
    category="media"
)
def youtube_set_volume(level: int) -> Dict[str, Any]:
    """Sets YouTube volume level."""
    global _YOUTUBE_VOLUME
    target = max(0, min(100, int(level)))
    _YOUTUBE_VOLUME = target
    return {"status": f"YouTube volume set to {target}%, sir.", "volume": target}

