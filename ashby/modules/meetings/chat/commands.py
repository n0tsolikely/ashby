from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ashby.interfaces.web.sessions import list_sessions
from ashby.modules.meetings.index import sqlite_fts
from ashby.modules.meetings.init_root import init_stuart_root
from ashby.modules.meetings.chat.retrieval import resolve_session_ref
from ashby.modules.meetings.schemas.chat import ChatActionOpenSessionV1, ChatReplyV1


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: List[str]
    raw: str


def parse_command(text: str) -> Optional[ParsedCommand]:
    raw = str(text or "").strip()
    if not raw.startswith("/"):
        return None
    tokens = raw[1:].split()
    if not tokens:
        return ParsedCommand(name="help", args=[], raw=raw)
    return ParsedCommand(name=tokens[0].lower(), args=tokens[1:], raw=raw)


def _help_text() -> str:
    return "\n".join(
        [
            "Supported commands:",
            "/help",
            "/sessions [query]",
            "/open <session_id|title>",
            "/rename_session <new title>",
            "/rename_formalization <run_id> <new title>",
            "/transcribe",
            "/formalize",
            "/export [full_bundle|transcript_only|formalization_only|dev_bundle]",
            "/map_speakers",
            "/set_speaker <label> <name>",
        ]
    )


def _indexed_sessions(limit: int = 200) -> List[Dict[str, Any]]:
    lay = init_stuart_root()
    conn = sqlite_fts.connect(sqlite_fts.get_db_path(stuart_root=lay.root))
    try:
        sqlite_fts.ensure_schema(conn)
        rows = sqlite_fts.list_sessions(conn, limit=max(int(limit), 1))
    finally:
        conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "session_id": r.session_id,
                "title": r.title,
                "mode": r.mode,
                "created_ts": r.created_ts,
            }
        )
    return out


def handle_command(
    cmd: ParsedCommand,
    *,
    ui_state: Optional[Dict[str, Any]] = None,
    sessions_index: Optional[List[Dict[str, Any]]] = None,
) -> ChatReplyV1:
    ui = dict(ui_state or {})
    sessions = list(sessions_index or list_sessions(limit=200))
    if not sessions:
        sessions = _indexed_sessions(limit=200)

    if cmd.name in {"help", "?"}:
        return ChatReplyV1(kind="assistant", text=_help_text())

    if cmd.name == "sessions":
        query = " ".join(cmd.args).strip().lower()
        rows = sessions
        if query:
            rows = [
                s
                for s in sessions
                if query in str(s.get("session_id") or "").lower() or query in str(s.get("title") or "").lower()
            ]
        rows = rows[:8]
        actions = [
            ChatActionOpenSessionV1(kind="open_session", session_id=str(s.get("session_id") or ""))
            for s in rows
            if str(s.get("session_id") or "").strip()
        ]
        if not rows:
            return ChatReplyV1(kind="assistant", text="No sessions found.", actions=[])
        lines = ["Sessions:"]
        for s in rows:
            lines.append(f"- {s.get('session_id')} | {s.get('title') or '(untitled)'}")
        return ChatReplyV1(kind="assistant", text="\n".join(lines), actions=actions)

    if cmd.name == "open":
        token = " ".join(cmd.args).strip()
        if not token:
            return ChatReplyV1(kind="clarify", text="Usage: /open <session_id|title>", clarify={"fields_needed": ["session_ref"]})
        resolved = resolve_session_ref(token, sessions)
        if not resolved:
            return ChatReplyV1(kind="assistant", text=f"No session matched: {token}")
        if len(resolved) > 1:
            options = [{"session_id": r.get("session_id"), "title": r.get("title")} for r in resolved[:10]]
            return ChatReplyV1(
                kind="clarify",
                text="Multiple sessions matched. Please choose one.",
                clarify={"fields_needed": ["session_ref"], "options": options},
            )
        sid = str(resolved[0].get("session_id") or "").strip()
        if not sid:
            return ChatReplyV1(kind="assistant", text="Matched row had no session_id.")
        return ChatReplyV1(
            kind="assistant",
            text=f"Opening session {sid}.",
            actions=[ChatActionOpenSessionV1(kind="open_session", session_id=sid)],
        )

    if cmd.name == "rename_session":
        title = " ".join(cmd.args).strip()
        if not title:
            return ChatReplyV1(kind="clarify", text="Usage: /rename_session <new title>", clarify={"fields_needed": ["title"]})
        return ChatReplyV1(kind="planner", text=f"Planned: rename selected session to '{title}'.", planner={"kind": "rename_session", "title": title})

    if cmd.name == "rename_formalization":
        if len(cmd.args) < 2:
            return ChatReplyV1(
                kind="clarify",
                text="Usage: /rename_formalization <run_id> <new title>",
                clarify={"fields_needed": ["run_id", "title"]},
            )
        run_id = cmd.args[0]
        title = " ".join(cmd.args[1:]).strip()
        return ChatReplyV1(
            kind="planner",
            text=f"Planned: rename run {run_id} to '{title}'.",
            planner={"kind": "rename_formalization", "run_id": run_id, "title": title},
        )

    if cmd.name in {"transcribe", "formalize"}:
        return ChatReplyV1(
            kind="planner",
            text=f"Planned: {cmd.name} using current UI selections. Send /confirm to execute.",
            planner={"kind": cmd.name, "ui_state": ui},
        )

    if cmd.name == "export":
        et = (cmd.args[0] if cmd.args else "full_bundle").strip().lower()
        if et not in {"full_bundle", "transcript_only", "formalization_only", "dev_bundle"}:
            return ChatReplyV1(kind="clarify", text="Usage: /export [full_bundle|transcript_only|formalization_only|dev_bundle]")
        return ChatReplyV1(kind="assistant", text=f"Export guidance: use export_type={et} in session export.")

    if cmd.name == "map_speakers":
        return ChatReplyV1(kind="planner", text="Planned: build/update speaker map for active transcript.", planner={"kind": "map_speakers"})

    if cmd.name == "set_speaker":
        if len(cmd.args) < 2:
            return ChatReplyV1(kind="clarify", text="Usage: /set_speaker <label> <name>", clarify={"fields_needed": ["label", "name"]})
        label = cmd.args[0]
        name = " ".join(cmd.args[1:]).strip()
        return ChatReplyV1(
            kind="planner",
            text=f"Planned: set {label} => {name}.",
            planner={"kind": "set_speaker", "label": label, "name": name},
        )

    return ChatReplyV1(kind="clarify", text=f"Unknown command '/{cmd.name}'. Use /help.")
