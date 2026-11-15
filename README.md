# MCP: Octopus Model Context Protocol

Octopus MCP is the pluggable tool execution engine for **ALFRED**, implementing Anthropic's Model Context Protocol (MCP) standard.

---

## Architecture Overview

1. **Intermediary Bridge (`MCP/bridge.py`)**:
   - Manages an isolated `asyncio` event loop in a daemon thread.
   - Provides a strictly synchronous API for ALFRED (`bridge.route_and_execute(query)` / `bridge.call_tool(name, args)`).
   - Keeps ALFRED synchronous, fast, and free of async loop complications.

2. **Dual-Mode Routing**:
   - **Step 1 (Fast-Path)**: Sub-1ms regex & keyword router checks obvious tool intents (`volume`, `search`, `open app`, `research`, `cancel research`).
   - **Step 2 (Quantized Classifier)**: Optional Qwen 4-bit / TurboQuant classifier (<30ms latency) for speech argument parsing.
   - **Step 3 (Graceful Fallback)**: If no tool matches or if a tool fails, returns `{"handled": False}`, cascading query to ALFRED's main LLM.

3. **Subprocess Pooling & Active Memory Management**:
   - External GitHub MCP servers run over **stdio** (Node.js / Python).
   - Injected Node memory cap: `--max-old-space-size=64`.
   - **Non-blocking Stderr Draining**: Background worker thread continuously drains child stderr pipes, preventing OS kernel pipe buffer deadlocks.
   - **Active Call Guarded Watchdog**: Subprocess idle watchdog respects in-flight tool executions, retiring processes safely after inactivity.
   - **orjson Serialization**: High-throughput JSON-RPC 2.0 communication.

4. **Deep Research & Job Control**:
   - Background deep research jobs with extended execution window (up to 15m) for multi-site synthesis.
   - Instant termination capability (`terminate_research`) with process tree termination, LLM RAM unloading, and automated temporary artifact purging.

---

## Directory Structure

```
MCP/
├── bridge.py              # Intermediary Sync-Async Bridge for ALFRED
├── mcp_servers.json       # Config registry for external GitHub stdio servers
├── core/
│   ├── client.py          # Fast orjson Stdio MCP Client with memory caps & stderr draining
│   ├── config.py          # Configuration and path management
│   ├── decorators.py      # @mcp_tool decorator for native in-process tools
│   ├── keyword_router.py  # Regex fast-path matcher with job cancellation rules
│   └── qwen_classifier.py # Qwen 4-bit quantized classifier interface
├── tools/                 # Native in-process Python tools
│   ├── device_tools.py    # Screen brightness & hardware controls
│   ├── email_tools.py     # OAuth2 Gmail query & inspection tools
│   ├── gui_tools.py       # Assistant state & HUD controls
│   ├── media_tools.py     # Audio ducking and media controls
│   ├── research_tools.py  # Deep research dispatch, report viewer & job termination
│   ├── resource_tools.py  # CPU/RAM system metric reporting
│   ├── system_tools.py    # Volume, power, and app lifecycle
│   ├── web_tools.py       # DuckDuckGo search integration
│   ├── window_tools.py    # Window manager and placement
│   └── youtube_tools.py   # YouTube search & video playback
└── README.md
```

---

## Adding External MCP Tools from GitHub

Open `MCP/mcp_servers.json` and add your tool definition under `mcpServers`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\%USERPROFILE%\\Desktop"],
      "enabled": true
    }
  }
}
```

The bridge automatically discovers schemas, enforces memory limits, runs the tool on demand, and retires the process after inactivity.
