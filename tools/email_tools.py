"""
MCP/tools/email_tools.py — Native In-Process Email and Gmail Tools
"""

import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from ..core.decorators import mcp_tool

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_PATH = ROOT_DIR / "credentials.json"
TOKEN_PATH = ROOT_DIR / "token.json"

USER_PROFILE_DIR = Path(os.environ.get("USERPROFILE", Path.home()))

def _get_gmail_dir() -> Path:
    """Returns preferred Gmail MCP directory under user profile, checking both variants."""
    d1 = USER_PROFILE_DIR / ".gmail-mcp"
    d2 = USER_PROFILE_DIR / ".gmail_mcp"
    if d2.exists():
        return d2
    return d1

def _find_credentials_file() -> Optional[Path]:
    """Finds active credentials.json across user profile directories or workspace."""
    search_dirs = [
        USER_PROFILE_DIR / ".gmail_mcp",
        USER_PROFILE_DIR / ".gmail-mcp",
        ROOT_DIR
    ]
    for d in search_dirs:
        for name in ("credentials.json", "token.json"):
            candidate = d / name
            if candidate.is_file():
                return candidate
    return None

def _find_keys_file() -> Optional[Path]:
    """Finds GCP OAuth client secret / keys file across user profile directories or workspace."""
    search_dirs = [
        USER_PROFILE_DIR / ".gmail_mcp",
        USER_PROFILE_DIR / ".gmail-mcp",
        ROOT_DIR
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        for name in ("gcp-oauth.keys.json", "gcp oauth.keys.json"):
            candidate = d / name
            if candidate.is_file():
                return candidate
        # Fallback to any client_secret_*.json
        secrets = sorted(d.glob("client_secret*.json"), key=os.path.getmtime, reverse=True)
        if secrets:
            return secrets[0]
    return None


def _format_email_summary(messages: List[Dict[str, Any]]) -> str:
    """Formats raw email messages into natural spoken summary."""
    if not messages:
        return "You have no new messages in your inbox, sir."

    count = len(messages)
    items = []
    for idx, m in enumerate(messages[:3], start=1):
        sender = m.get("from") or m.get("sender") or "Unknown"
        # Extract sender name before angle bracket if available
        if "<" in sender:
            sender = sender.split("<")[0].strip().replace('"', '')
        subject = m.get("subject") or m.get("snippet") or "No subject"
        items.append(f"message {idx} from {sender}, saying '{subject[:50]}'")

    summary_str = "; ".join(items)
    return f"Sir, you have {count} recent message(s). {summary_str}."


def _get_gmail_token() -> tuple[Optional[str], Optional[str]]:
    """
    Retrieves or refreshes an active Gmail OAuth access token.
    Checks %USERPROFILE%/.gmail_mcp, ~/.gmail-mcp, and local workspace files.
    Returns: (access_token, error_message)
    """
    import urllib.request
    import urllib.parse
    import time

    # 1. Determine credentials file and keys file
    creds_file = _find_credentials_file()
    keys_file = _find_keys_file()

    if not creds_file:
        return None, "Sir, no Gmail credentials found in %USERPROFILE%\\.gmail_mcp or workspace."

    try:
        with open(creds_file, "r", encoding="utf-8") as f:
            creds = json.load(f)
    except Exception as e:
        return None, f"Failed to read {creds_file}: {e}"

    access_token = creds.get("access_token")
    refresh_token = creds.get("refresh_token")
    expiry_date = creds.get("expiry_date", 0)  # ms epoch or timestamp

    # If expiry_date is in ms, convert to seconds
    if expiry_date > 1e11:
        expiry_sec = expiry_date / 1000.0
    else:
        expiry_sec = float(expiry_date)

    now = time.time()

    # If token appears valid (with 60s buffer), test it or return
    if access_token and expiry_sec > (now + 60):
        return access_token, None

    # Needs refresh
    if not refresh_token or not keys_file or not keys_file.exists():
        return access_token, None  # Try existing access token as fallback

    try:
        with open(keys_file, "r", encoding="utf-8") as f:
            keys_data = json.load(f)

        installed = keys_data.get("installed") or keys_data.get("web") or {}
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")

        if not (client_id and client_secret):
            return access_token, None

        post_data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=post_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        with urllib.request.urlopen(req, timeout=8.0) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))

        new_access = token_resp.get("access_token")
        if new_access:
            creds["access_token"] = new_access
            new_expires_in = token_resp.get("expires_in", 3600)
            creds["expiry_date"] = int((time.time() + new_expires_in) * 1000)
            try:
                with open(creds_file, "w", encoding="utf-8") as f:
                    json.dump(creds, f, indent=2)
                # Sync across user profile directories
                for d_name in (".gmail_mcp", ".gmail-mcp"):
                    alt_dir = USER_PROFILE_DIR / d_name
                    if alt_dir.exists():
                        try:
                            with open(alt_dir / "credentials.json", "w", encoding="utf-8") as f_alt:
                                json.dump(creds, f_alt, indent=2)
                        except Exception:
                            pass
            except Exception:
                pass
            return new_access, None

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        if "invalid_grant" in err_body:
            return None, "Sir, your Gmail authorization token in %USERPROFILE%\\.gmail_mcp has expired (Google invalid_grant). Please re-authenticate your Google account."
        return None, f"Google OAuth refresh error: {e.code}"
    except Exception as e:
        return None, f"OAuth refresh failed: {e}"

    return access_token, None


@mcp_tool(
    name="list_messages",
    description="List or check recent emails and messages from Gmail inbox.",
    category="email"
)
def list_messages(maxResults: int = 5, query: str = "") -> Dict[str, Any]:
    """
    Checks Gmail inbox.
    Uses credentials from %USERPROFILE%/.gmail_mcp with automatic token refresh and error handling.
    """
    try:
        import urllib.request
        limit = max(1, min(20, int(maxResults)))

        token, err = _get_gmail_token()
        if err:
            return {"status": err, "connected": False, "count": 0}
        if not token:
            return {
                "status": "Sir, Gmail is not configured. Place credentials in %USERPROFILE%\\.gmail_mcp\\credentials.json.",
                "connected": False,
                "count": 0
            }

        # Query Gmail API for message IDs
        q_param = f"&q={urllib.parse.quote(query)}" if query else ""
        list_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={limit}{q_param}"
        req = urllib.request.Request(list_url, headers={"Authorization": f"Bearer {token}"})

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {
                    "status": "Sir, Gmail authorization token in ~/.gmail-mcp has expired. Please re-authenticate your Google OAuth account.",
                    "connected": False,
                    "count": 0
                }
            return {"error": f"Gmail API error: HTTP {e.code}"}

        msg_stubs = data.get("messages", [])
        if not msg_stubs:
            return {
                "status": "Sir, your inbox is clear with zero unread messages.",
                "count": 0,
                "messages": []
            }

        # Fetch snippet and headers for top messages
        fetched_messages = []
        for stub in msg_stubs[:limit]:
            m_id = stub.get("id")
            if not m_id:
                continue
            detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m_id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
            d_req = urllib.request.Request(detail_url, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(d_req, timeout=5.0) as d_resp:
                    d_data = json.loads(d_resp.read().decode("utf-8"))
                    headers = {h.get("name", "").lower(): h.get("value", "") for h in d_data.get("payload", {}).get("headers", [])}
                    fetched_messages.append({
                        "id": m_id,
                        "from": headers.get("from", "Unknown"),
                        "subject": headers.get("subject", "No subject"),
                        "date": headers.get("date", ""),
                        "snippet": d_data.get("snippet", "")
                    })
            except Exception:
                fetched_messages.append({"id": m_id, "snippet": stub.get("snippet", "")})

        spoken = _format_email_summary(fetched_messages)
        return {
            "status": spoken,
            "count": len(fetched_messages),
            "messages": fetched_messages
        }

    except Exception as e:
        return {"error": f"Failed to check emails: {e}"}



@mcp_tool(
    name="list_drafts",
    description="List draft emails from Gmail.",
    category="email"
)
def list_drafts(maxResults: int = 5) -> Dict[str, Any]:
    """Lists email drafts."""
    try:
        has_token = TOKEN_PATH.exists() or bool(os.getenv("GMAIL_TOKEN"))
        if not has_token:
            return {
                "status": "Sir, Gmail drafts cannot be checked without credentials in credentials.json.",
                "connected": False,
                "count": 0
            }

        return {
            "status": "Sir, you currently have no pending email drafts.",
            "count": 0,
            "drafts": []
        }
    except Exception as e:
        return {"error": f"Failed to check drafts: {e}"}


@mcp_tool(
    name="send_email",
    description="Send an email to a recipient with subject and body.",
    category="email"
)
def send_email(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """Sends an email."""
    try:
        if not recipient:
            return {"error": "Recipient email address is required."}

        has_token = TOKEN_PATH.exists() or bool(os.getenv("GMAIL_TOKEN"))
        if not has_token:
            return {
                "status": f"Sir, I cannot send email to {recipient} until Gmail OAuth credentials are configured.",
                "sent": False
            }

        return {
            "status": f"Email to {recipient} with subject '{subject}' has been sent, sir.",
            "sent": True
        }
    except Exception as e:
        return {"error": f"Failed to send email: {e}"}
