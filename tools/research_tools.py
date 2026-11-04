"""
MCP/tools/research_tools.py — Native MCP Tool Adapter for Detachable Researcher
"""

import os
import threading
import webbrowser
from typing import Dict, Any, Optional
from ..core.decorators import mcp_tool
from FILES.logger import get_logger

logger = get_logger(__name__)

# Workspace path resolution
_WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESEARCHER_DIR = os.path.join(_WORKSPACE_ROOT, "Researcher")
VAULT_DIR = os.path.join(_WORKSPACE_ROOT, "Vault")

# Thread-safe notification queue for background research completions
_COMPLETED_RESEARCH_NOTIFICATIONS = []
_ACTIVE_RESEARCH_JOBS = {}


def is_researcher_available() -> bool:
    """Checks whether the Researcher repository is present on disk."""
    return os.path.isdir(RESEARCHER_DIR)


def pop_research_notification() -> Optional[str]:
    """Retrieves next pending research completion notification for ALFRED voice."""
    if _COMPLETED_RESEARCH_NOTIFICATIONS:
        return _COMPLETED_RESEARCH_NOTIFICATIONS.pop(0)
    return None


@mcp_tool(
    name="start_deep_research",
    description="Starts an iterative deep research job on a given topic in the background, updating Obsidian vault and generating exports.",
    category="research"
)
def start_deep_research(topic: str, max_sites: int = 3) -> Dict[str, Any]:
    """Launches research via stdio MCP server or triggers graceful LLM fallback if missing."""
    clean_topic = topic.strip().strip("'\"")
    if not clean_topic:
        return {"error": "Topic cannot be empty."}

    # 1. Fallback if Researcher repository is NOT present
    if not is_researcher_available():
        logger.warning(f"Researcher repository not found. Triggering LLM fallback prompt for query: '{clean_topic}'")
        try:
            from FILES.utils import Responder
            prompt = (
                f"The researcher does not exist in ALFRED's program, failed to do research due to Researcher not found error. "
                f"The user requested research on: '{clean_topic}'. "
                f"Politely explain to the user that deep multi-source research failed because the Researcher repository is not present in ALFRED's program folder. "
                f"If providing brief context about the topic, strictly avoid authoritative claims and begin your context with "
                f"'As of last from what I heard, from data...' or directly state that deep research cannot be completed without the Researcher module."
            )
            fallback_speech = Responder(prompt)
            return {"status": fallback_speech, "keep_ui": True}
        except Exception as e:
            logger.error(f"Error calling LLM fallback: {e}")
            return {
                "status": (
                    f"Sir, the researcher does not exist in ALFRED's program. "
                    f"I failed to do research on '{clean_topic}' due to a Researcher not found error."
                ),
                "keep_ui": True
            }

    # 2. Researcher IS present -> Execute asynchronously via MCP Stdio Server
    job_id = f"research_{clean_topic.replace(' ', '_').lower()}"

    if job_id in _ACTIVE_RESEARCH_JOBS and _ACTIVE_RESEARCH_JOBS[job_id].get("status") == "running":
        return {
            "status": f"Sir, research on '{clean_topic}' is already running in the background.",
            "keep_ui": True
        }

    _ACTIVE_RESEARCH_JOBS[job_id] = {
        "status": "running",
        "topic": clean_topic
    }

    def _worker():
        try:
            logger.info(f"[Background Research] Dispatching deep research for '{clean_topic}' to stdio MCP server...")
            from ..bridge import get_bridge
            bridge = get_bridge()

            # Call researcher stdio server tool
            tool_name = "researcher__deep_research" if "researcher__deep_research" in bridge._tools_cache else "deep_research"
            res = bridge.call_tool(tool_name, {"topic": clean_topic, "max_sites": max_sites}, timeout=300.0)

            _ACTIVE_RESEARCH_JOBS[job_id] = {
                "status": "completed",
                "result": res
            }
            notification_msg = (
                f"Sir, the deep research on {clean_topic} is done. "
                "Shall I open Obsidian to view the note, or shall I make a webpage and PDF report?"
            )
            _COMPLETED_RESEARCH_NOTIFICATIONS.append(notification_msg)
            logger.info(f"[Background Research] Completed research on '{clean_topic}'. Enqueued notification.")
        except Exception as e:
            logger.error(f"[Background Research] Failed research on '{clean_topic}': {e}", exc_info=True)
            _ACTIVE_RESEARCH_JOBS[job_id] = {
                "status": "failed",
                "error": str(e)
            }
            _COMPLETED_RESEARCH_NOTIFICATIONS.append(
                f"Sir, I encountered an issue during the research on {clean_topic}."
            )

    t = threading.Thread(target=_worker, daemon=True, name=f"ResearcherWorker-{clean_topic}")
    t.start()

    return {
        "status": (
            f"Starting deep research on '{clean_topic}' in the background, sir. "
            "While doing that, do you have any other thing you want me to do?"
        ),
        "job_id": job_id,
        "keep_ui": True
    }


@mcp_tool(
    name="open_obsidian_vault",
    description="Opens the Obsidian research vault or a specific research markdown note.",
    category="research"
)
def open_obsidian_vault(note_name: Optional[str] = None) -> Dict[str, Any]:
    """Opens Obsidian or opens the note file in default editor."""
    if not os.path.isdir(VAULT_DIR):
        return {"error": "Vault directory not found."}

    if note_name:
        clean_name = note_name.strip()
        if not clean_name.endswith(".md"):
            clean_name = f"Research_{clean_name.replace(' ', '_')}.md"
        target_path = os.path.join(VAULT_DIR, clean_name)
        if os.path.isfile(target_path):
            os.system(f'start "" "{target_path}"')
            return {"status": f"Opening note {clean_name} for you, sir."}

    os.system(f'start "" "{VAULT_DIR}"')
    return {"status": "Opened the Obsidian Research Vault, sir."}


@mcp_tool(
    name="open_research_report",
    description="Opens the generated showcase webpage or PDF export for a research topic.",
    category="research"
)
def open_research_report(topic: Optional[str] = None, format_type: str = "html") -> Dict[str, Any]:
    """Opens export file in default browser."""
    exports_dir = os.path.join(RESEARCHER_DIR, "Exports")
    if not os.path.isdir(exports_dir):
        return {"error": "No exports directory found."}

    files = [os.path.join(exports_dir, f) for f in os.listdir(exports_dir) if f.endswith(f".{format_type}")]
    if not files:
        files = [os.path.join(exports_dir, f) for f in os.listdir(exports_dir) if f.endswith((".html", ".pdf"))]

    if not files:
        return {"error": "No generated research reports found, sir."}

    target_file = files[-1]
    if topic:
        clean_topic = topic.lower().replace(" ", "_")
        matched = [f for f in files if clean_topic in f.lower()]
        if matched:
            target_file = matched[-1]

    webbrowser.open(f"file:///{target_file.replace(os.sep, '/')}")
    ext_label = "PDF report" if target_file.endswith(".pdf") else "interactive web view"
    return {"status": f"Opening the {ext_label} for you now, sir."}
