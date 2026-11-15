"""
MCP/core/client.py — High-Performance Stdio MCP Client with orjson, Memory Management, and Non-blocking Stderr Draining
"""

import os
import sys
import gc
import time
import subprocess
import threading
from typing import Optional, List, Dict, Any

try:
    import orjson
except ImportError:
    import json
    class _OrjsonCompat:
        @staticmethod
        def dumps(obj):
            return json.dumps(obj).encode('utf-8')
        @staticmethod
        def loads(b):
            return json.loads(b)
    orjson = _OrjsonCompat()

from .config import get_settings
from FILES.logger import get_logger

logger = get_logger("MCP.StdioClient")


class StdioMCPClient:
    """
    Manages an individual external MCP server running over stdio.
    Features:
    - orjson serialization for ultra-fast JSON-RPC
    - Automatic Node.js memory limits (--max-old-space-size=64)
    - Subprocess lifecycle management with idle termination (default 60s)
    - Continuous stderr draining thread to prevent OS kernel pipe buffer deadlocks
    - gc.collect() on process retirement
    """

    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        self.name = name
        self.base_command = command
        self.base_args = list(args)
        self.env = env or os.environ.copy()
        self.cwd = os.path.abspath(cwd) if cwd else None
        
        settings = get_settings()
        self.idle_timeout = settings.get("idle_timeout_seconds", 120)
        self.node_max_old_space = settings.get("node_max_old_space_size_mb", 64)
        self.aggressive_gc = settings.get("aggressive_gc", True)

        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._last_used: float = 0.0
        self._request_id = 0
        self._cached_tools: List[Dict[str, Any]] = []
        self._watchdog_timer: Optional[threading.Timer] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._active_calls: int = 0

    def _prepare_command_args(self) -> List[str]:
        """Injects Node.js memory caps if command is node or npx."""
        cmd = self.base_command.lower()
        args = list(self.base_args)

        if cmd in ("node", "node.exe"):
            memory_flag = f"--max-old-space-size={self.node_max_old_space}"
            if memory_flag not in args:
                args.insert(0, memory_flag)
        elif cmd in ("npx", "npx.cmd"):
            # Set NODE_OPTIONS for npx subprocesses
            current_options = self.env.get("NODE_OPTIONS", "")
            memory_flag = f"--max-old-space-size={self.node_max_old_space}"
            if memory_flag not in current_options:
                self.env["NODE_OPTIONS"] = f"{current_options} {memory_flag}".strip()

        import shutil
        executable = shutil.which(self.base_command) or self.base_command
        return [executable] + args

    def _drain_stderr(self, proc: subprocess.Popen):
        """Continuously reads proc.stderr to prevent OS pipe buffer deadlocks."""
        try:
            for raw_line in iter(proc.stderr.readline, b""):
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    if "[ERROR]" in line:
                        logger.error(f"[{self.name} stderr] {line}")
                    elif "[WARNING]" in line:
                        logger.warning(f"[{self.name} stderr] {line}")
                    elif "[INFO]" in line or f"[{self.name}." in line.lower() or "researcher" in line.lower():
                        logger.info(f"[{self.name} stderr] {line}")
                    else:
                        logger.debug(f"[{self.name} stderr] {line}")
        except Exception:
            pass

    def _ensure_process(self) -> subprocess.Popen:
        """Spawns the child process if not running, drains stderr, and completes handshake."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._reset_idle_watchdog()
                return self._process

            full_cmd = self._prepare_command_args()
            self._process = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
                cwd=self.cwd,
                bufsize=0
            )

            # Launch background thread to drain stderr pipe and prevent buffer deadlocks
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(self._process,),
                daemon=True,
                name=f"MCP-StderrDrainer-{self.name}"
            )
            self._stderr_thread.start()

            # Perform MCP Handshake
            self._send_handshake()
            self._reset_idle_watchdog()
            return self._process

    def _reset_idle_watchdog(self):
        """Reschedules process shutdown timer."""
        self._last_used = time.time()
        if self._watchdog_timer:
            self._watchdog_timer.cancel()

        if self.idle_timeout > 0:
            self._watchdog_timer = threading.Timer(self.idle_timeout, self._check_idle_and_retire)
            self._watchdog_timer.daemon = True
            self._watchdog_timer.start()

    def _check_idle_and_retire(self):
        """Terminates subprocess if idle for longer than idle_timeout and no active calls."""
        with self._lock:
            if self._process is None:
                return

            if self._active_calls > 0:
                # Do not retire while calls are actively processing
                self._reset_idle_watchdog()
                return

            idle_duration = time.time() - self._last_used
            if idle_duration >= self.idle_timeout:
                self.terminate()

    def terminate(self):
        """Kills the running subprocess tree and runs garbage collection."""
        with self._lock:
            if self._watchdog_timer:
                self._watchdog_timer.cancel()
                self._watchdog_timer = None

            if self._process is not None:
                proc = self._process
                self._process = None
                try:
                    if sys.platform == "win32":
                        # Terminate full process tree on Windows to clean up child python.exe processes
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3.0
                        )
                    else:
                        proc.terminate()
                        proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            if self.aggressive_gc:
                gc.collect()

    def _send_raw(self, message: Dict[str, Any]) -> None:
        """Writes orjson bytes directly into stdin pipe with trailing newline."""
        payload = orjson.dumps(message) + b"\n"
        if self._process and self._process.stdin:
            self._process.stdin.write(payload)
            self._process.stdin.flush()

    def _read_raw(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Reads a JSON-RPC line from stdout."""
        if not self._process or not self._process.stdout:
            return None

        line = self._process.stdout.readline()
        if not line:
            return None
        return orjson.loads(line)

    def _send_handshake(self):
        """Standard MCP initialization exchange."""
        self._request_id += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "octopus-mcp", "version": "1.0.0"}
            }
        }
        self._send_raw(init_req)
        resp = self._read_raw(timeout=5.0)

        # Notify initialized
        self._send_raw({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Lists tools with schema caching."""
        if self._cached_tools and not force_refresh:
            return self._cached_tools

        proc = self._ensure_process()
        self._request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/list",
            "params": {}
        }
        self._send_raw(req)
        resp = self._read_raw()
        if resp and "result" in resp and "tools" in resp["result"]:
            self._cached_tools = resp["result"]["tools"]
            return self._cached_tools
        return []

    def call_tool(self, name: str, arguments: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Executes a tool on the external MCP server with busy-state tracking."""
        with self._lock:
            self._active_calls += 1
            if self._watchdog_timer:
                self._watchdog_timer.cancel()

        try:
            self._ensure_process()
            self._request_id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments
                }
            }
            self._send_raw(req)
            resp = self._read_raw(timeout=timeout)

            if not resp:
                return {"success": False, "error": f"Tool '{name}' timed out or server failed."}
            if "error" in resp:
                return {"success": False, "error": resp["error"]}
            return {"success": True, "result": resp.get("result", {})}
        finally:
            with self._lock:
                self._active_calls = max(0, self._active_calls - 1)
                self._reset_idle_watchdog()
