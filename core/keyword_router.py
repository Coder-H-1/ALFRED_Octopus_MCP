"""
MCP/core/keyword_router.py — Strategy B Fast-Path Intent & Keyword Matcher
"""

import re
from typing import Dict, Any, Optional, Tuple, List

class KeywordRouter:
    """
    Sub-1ms keyword and regex rule matcher.
    Extracts tool targets and basic arguments from obvious voice/text commands.
    """

    def __init__(self):
        self._rules: List[Tuple[re.Pattern, str, Any]] = []
        self._init_default_rules()

    def _init_default_rules(self):
        # 1. Volume Control: "set volume to 50", "volume 80", "mute volume"
        def extract_volume(m: re.Match) -> Dict[str, Any]:
            val = m.group(1)
            if val.lower() == "mute":
                return {"level": 0}
            return {"level": int(val)}

        self.register_rule(
            r"(?:set\s+)?volume\s+(?:to\s+)?(mute|\d+)",
            "system_set_volume",
            extract_volume
        )

        def extract_volume_adjust(m: re.Match) -> Dict[str, Any]:
            text = m.group(0).lower()
            direction = "increase" if any(w in text for w in ["up", "louder", "raise", "increase"]) else "decrease"
            return {"direction": direction}

        self.register_rule(
            r"(?:volume\s+(?:up|down)|turn\s+(?:the\s+)?volume\s+(?:up|down)|(?:increase|decrease|raise|lower)\s+(?:the\s+)?volume|louder|quieter)",
            "system_adjust_volume",
            extract_volume_adjust
        )

        self.register_rule(
            r"(?:mute\s+(?:audio|volume|sound)|unmute\s+(?:audio|volume|sound)|^mute$|^unmute$)",
            "system_mute_volume",
            lambda m: {}
        )

        # 2. YouTube Playback
        ORDINAL_MAP = {
            "first": 1, "1st": 1,
            "second": 2, "2nd": 2,
            "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6,
            "seventh": 7, "7th": 7,
            "eighth": 8, "8th": 8,
            "ninth": 9, "9th": 9,
        }

        def extract_youtube(m: re.Match) -> Dict[str, Any]:
            full_text = m.string.lower()
            groups = [g for g in m.groups() if g]
            raw_q = str(groups[0]).strip() if groups else ""

            # Check if user requested to show list in query
            show_list = bool(re.search(r"\b(?:show\s+(?:the\s+)?list|show\s+options|display\s+list|list\s+options|show\s+results)\b", full_text))

            # Detect song number/index (defaults to 1st in the list)
            target_index = 1
            explicit_index = False
            ord_match = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th)\b", full_text)
            if ord_match:
                target_index = ORDINAL_MAP.get(ord_match.group(1).lower(), 1)
                explicit_index = True
            else:
                num_match = re.search(r"\b(?:song|number|track|option|item)\s*(?:no\.?|number)?\s*(\d+)\b", full_text)
                if num_match:
                    try:
                        target_index = int(num_match.group(1))
                        explicit_index = True
                    except Exception:
                        target_index = 1

            # Clean query by removing list keywords, ordinals, numbers, and prefixes
            clean_q = raw_q
            clean_q = re.sub(r"\b(?:and\s+)?(?:show\s+(?:the\s+)?list|show\s+options|display\s+list|list\s+options|show\s+results)\b", "", clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th)\s+(?:song|video|track|option)?\s*(?:of|from)?\b", "", clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r"\b(?:song|number|track|option|item)\s*(?:no\.?|number)?\s*\d+\s*(?:of|from)?\b", "", clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r"\b(?:on|from|in)?\s*youtube\b", "", clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r"^\s*(?:song|video|track|music)\s+", "", clean_q, flags=re.IGNORECASE)
            clean_q = re.sub(r"\s+", " ", clean_q).strip(" ,.-")

            if not clean_q:
                clean_q = raw_q.strip()

            return {
                "query": clean_q,
                "index": target_index,
                "show_list": show_list,
                "explicit_index": explicit_index
            }

        # 2a. Pre-list query: "show list and play <song>"
        self.register_rule(
            r"(?:show\s+(?:the\s+)?list|show\s+options|display\s+list)\s+(?:and\s+)?(?:then\s+)?play\s+(.+)",
            "youtube_play",
            extract_youtube
        )

        # 2b. Standard YouTube query: "play <song> on youtube [and show list]"
        self.register_rule(
            r"(?:play\s+(.+?)\s+(?:on|from)\s+youtube.*|play\s+youtube\s+(.+)|on\s+youtube\s+play\s+(.+))",
            "youtube_play",
            extract_youtube
        )

        # 2c. Direct song query: "play song <song>" or "play track <song>"
        self.register_rule(
            r"(?:play\s+song\s+(.+)|play\s+track\s+(.+))",
            "youtube_play",
            extract_youtube
        )

        self.register_rule(
            r"(?:stop\s+youtube|close\s+youtube|end\s+youtube|stop\s+music)",
            "youtube_stop",
            lambda m: {}
        )

        self.register_rule(
            r"(?:set\s+)?youtube\s+volume\s+(?:to\s+)?(\d+)",
            "youtube_set_volume",
            lambda m: {"level": int(m.group(1))}
        )

        # 3. Web Search & Wikipedia Extraction
        def extract_search(m: re.Match) -> Dict[str, Any]:
            return {"query": m.group(1).strip()}

        self.register_rule(
            r"\b(?:search(?:\s+for|\s+web)?|google|look\s+up|who\s+is|what\s+is|tell\s+me\s+about)\s+(.+)",
            "web_search_extract",
            extract_search
        )

        # 4. Workspace & Desktop
        self.register_rule(
            r"(?:open|launch|start)\s+(?:the\s+)?(?:workspace|workplace|work\s+space|work\s+place)",
            "workspace_open",
            lambda m: {}
        )
        self.register_rule(
            r"(?:close|exit|terminate|kill)\s+(?:the\s+)?(?:workspace|workplace|work\s+space|work\s+place)",
            "workspace_close",
            lambda m: {}
        )
        self.register_rule(
            r"(?:go\s+to|show)\s+(?:the\s+)?(?:desktop|main\s+screen)",
            "desktop_show",
            lambda m: {}
        )

        # 5. Application Launcher
        def extract_app(m: re.Match) -> Dict[str, Any]:
            return {"app_name": m.group(1).strip()}

        self.register_rule(
            r"(?:open|launch|start)\s+([a-zA-Z0-9_\-\s]+)",
            "app_open",
            extract_app
        )

        # 5. Resource Monitoring
        self.register_rule(
            r"(?:check\s+)?(?:system\s+status|system\s+health|resource\s+status)",
            "get_resource_summary",
            lambda m: {}
        )
        self.register_rule(
            r"(?:check\s+)?(?:cpu\s+usage|ram\s+usage|memory\s+usage)",
            "get_system_resources",
            lambda m: {}
        )
        self.register_rule(
            r"(?:check\s+)?process\s+(?:memory|usage|resources)",
            "get_process_resources",
            lambda m: {}
        )

        # 6. Battery & Brightness
        self.register_rule(
            r"(?:check\s+)?battery(?:\s+status|\s+level|\s+percentage)?|how\s+much\s+battery",
            "get_battery_status",
            lambda m: {}
        )
        self.register_rule(
            r"(?:set\s+)?brightness\s+(?:to\s+)?(\d+)",
            "set_screen_brightness",
            lambda m: {"level": int(m.group(1))}
        )

        def extract_brightness_adjust(m: re.Match) -> Dict[str, Any]:
            text = m.group(0).lower()
            direction = "increase" if any(w in text for w in ["up", "raise", "increase", "bright"]) else "decrease"
            return {"direction": direction}

        self.register_rule(
            r"(?:brightness\s+(?:up|down)|turn\s+(?:the\s+)?brightness\s+(?:up|down)|(?:increase|decrease|raise|lower)\s+(?:the\s+)?brightness|dim\s+screen|brighten\s+screen)",
            "adjust_screen_brightness",
            extract_brightness_adjust
        )

        self.register_rule(
            r"(?:check|get|what\s+is\s+(?:the\s+)?|current\s+)?(?:screen\s+)?brightness",
            "get_screen_brightness",
            lambda m: {}
        )

        # 7. Window Management (Native Desktop & Dynamic GUI)
        def extract_window_state(m: re.Match) -> Dict[str, Any]:
            return {"action": m.group(1), "window_name": m.group(2).strip()}

        self.register_rule(
            r"(minimize|maximize|restore)\s+(?:window\s+)?(.+)",
            "window_manage_state",
            extract_window_state
        )

        def extract_bring_front(m: re.Match) -> Dict[str, Any]:
            return {"window_name": m.group(1).strip()}

        self.register_rule(
            r"(?:switch\s+to|bring\s+(.+?)\s+(?:to\s+front|to\s+the\s+front|forward))",
            "window_bring_to_front",
            extract_bring_front
        )

        # Dynamic IGUIRS GUI Window Tools
        def extract_create_win(m: re.Match) -> Dict[str, Any]:
            name = m.group(1).strip()
            w = int(m.group(2)) if m.group(2) else 800
            h = int(m.group(3)) if m.group(3) else 600
            return {"name": name, "width": w, "height": h}

        self.register_rule(
            r"(?:create|spawn|open)\s+(?:a\s+)?(?:gui\s+)?window\s+([a-zA-Z0-9_\-]+)(?:\s+(\d+)\s+(\d+))?",
            "gui_create_window",
            extract_create_win
        )

        def extract_check_win(m: re.Match) -> Dict[str, Any]:
            return {"name": m.group(1).strip()}

        self.register_rule(
            r"(?:check|get|show)\s+(?:gui\s+)?window\s+status(?:\s+for)?\s+([a-zA-Z0-9_\-]+)",
            "gui_check_window_status",
            extract_check_win
        )

        def extract_close_win(m: re.Match) -> Dict[str, Any]:
            return {"name": m.group(1).strip()}

        self.register_rule(
            r"(?:close|exit|terminate|kill)\s+(?:gui\s+)?window\s+([a-zA-Z0-9_\-]+)",
            "gui_close_window",
            extract_close_win
        )

        def extract_clean_win(m: re.Match) -> Dict[str, Any]:
            target = m.group(1).strip() if m.group(1) else "all"
            return {"name": target}

        self.register_rule(
            r"(?:clean|clear)\s+(?:gui\s+)?windows?(?:\s+([a-zA-Z0-9_\-]+))?",
            "gui_clean_window",
            extract_clean_win
        )

        def extract_resize_win(m: re.Match) -> Dict[str, Any]:
            name = m.group(1).strip()
            w = int(m.group(2))
            h = int(m.group(3))
            return {"name": name, "new_width": w, "new_height": h}

        self.register_rule(
            r"(?:resize|update)\s+(?:gui\s+)?window\s+([a-zA-Z0-9_\-]+)\s+(?:to\s+)?(\d+)\s*(?:by|x|\s+)\s*(\d+)",
            "gui_update_dimension",
            extract_resize_win
        )

        # 8. Media Controls
        self.register_rule(
            r"(?:pause|resume|toggle\s+media|play\s+media|pause\s+media|pause\s+music|resume\s+music)",
            "media_play_pause",
            lambda m: {}
        )
        self.register_rule(
            r"(?:next\s+song|next\s+track|skip\s+song|skip\s+track)",
            "media_next",
            lambda m: {}
        )
        self.register_rule(
            r"(?:previous\s+song|previous\s+track|last\s+song)",
            "media_previous",
            lambda m: {}
        )
        self.register_rule(
            r"(?:stop\s+media|stop\s+music)",
            "media_stop",
            lambda m: {}
        )

        # 9. Deep Research Cancellation & Termination (Higher priority than general app_close)
        def extract_cancel_topic(m: re.Match) -> dict:
            try:
                raw = m.group(1).strip() if m.lastindex and m.group(1) else ""
                clean = re.sub(r"^(?:on|about|regarding)\s+", "", raw, flags=re.IGNORECASE).strip()
                if clean:
                    return {"topic": clean}
            except Exception:
                pass
            return {}

        self.register_rule(
            r"(?:cancel|terminate|stop|abort|kill|clear)\s+(?:all\s+)?(?:the\s+)?(?:background\s+)?(?:deep\s+)?research(?:es)?(?:\s+(?:on|about|regarding)?\s*(.+))?",
            "terminate_research",
            extract_cancel_topic
        )

        # 10. Application Closer
        def extract_close_app(m: re.Match) -> Dict[str, Any]:
            return {"app_name": m.group(1).strip()}

        self.register_rule(
            r"(?:close|exit|terminate|kill)\s+([a-zA-Z0-9_\-\s]+)",
            "app_close",
            extract_close_app
        )

        # 11. Gmail / Email Controls
        self.register_rule(
            r"(?:check|list|get|show|read)\s+(?:my\s+)?(?:emails?|messages?|inbox|mail|gmail)",
            "list_messages",
            lambda m: {"maxResults": 5}
        )
        self.register_rule(
            r"(?:check|list|get|show)\s+(?:my\s+)?(?:drafts|email\s+drafts)",
            "list_drafts",
            lambda m: {"maxResults": 5}
        )

        # 12. Deep Research Controls
        def extract_research_topic(m: re.Match) -> dict:
            raw = m.group(1).strip()
            clean = re.sub(r"^(?:on|about|regarding)\s+", "", raw, flags=re.IGNORECASE).strip()
            return {"topic": clean}

        self.register_rule(
            r"(?:do\s+a?\s*)?deep\s+research\s+(?:on|about)?\s*(.+)",
            "start_deep_research",
            extract_research_topic
        )
        self.register_rule(
            r"^research\s+(?:on|about)?\s*(.+)",
            "start_deep_research",
            extract_research_topic
        )

        # 11. Obsidian & Research Exports
        self.register_rule(
            r"^(?:open|view|launch)\s+obsidian(?:\s+vault)?",
            "open_obsidian_vault",
            lambda m: {}
        )
        self.register_rule(
            r"(?:open|view|show)\s+(?:the\s+)?research\s+(?:report|webpage|pdf|page)",
            "open_research_report",
            lambda m: {}
        )


    def register_rule(self, pattern: str, tool_name: str, extractor_fn):
        """Registers a new fast-path regex rule."""
        compiled = re.compile(pattern, re.IGNORECASE)
        self._rules.append((compiled, tool_name, extractor_fn))

    def match(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Tests text against fast rules.
        Returns tool name and extracted arguments if matched, else None.
        """
        clean_text = text.strip()
        for pattern, tool_name, extractor in self._rules:
            m = pattern.search(clean_text)
            if m:
                try:
                    args = extractor(m)
                    return {
                        "matched": True,
                        "tool_name": tool_name,
                        "arguments": args,
                        "strategy": "keyword_fast_path"
                    }
                except Exception:
                    continue
        return None
