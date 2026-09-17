"""Saved chats: one append-only JSONL transcript per session.

  ~/.agents/sessions/<project>/<session id>.jsonl

<project> is the launch directory flattened into one folder name, so each
project lists only its own chats. Every line is a message, appended as the
conversation grows. Changes to earlier history are appended as entries
rather than made by editing the file, so nothing written is ever lost:

  {"rewind_to": n}     keep only the first n messages      (/rewind)
  {"replace": [...]}   the conversation is now this list   (compaction)

load() replays the file. Tool results are saved in full — history.strip
shortens them again after loading.

Separate from log.py's run log: that records every event for debugging,
this records only what is needed to carry a conversation on.
"""

import json
import re
import time
import uuid
from pathlib import Path


def sessions_dir():
    project = re.sub(r"[^A-Za-z0-9]+", "-", str(Path.cwd().resolve())).strip("-")
    return Path.home() / ".agents" / "sessions" / project


def _new_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def load(path):
    """Replay a session file into its message list."""
    messages = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # A half-written last line from a killed process. Skipping it
            # costs one message; raising would break listing every session.
            continue
        if "rewind_to" in entry:
            del messages[entry["rewind_to"]:]
        elif "replace" in entry:
            messages = list(entry["replace"])
        else:
            messages.append(entry)
    return messages


def title(messages):
    """The first user message, on one line, without attachments."""
    for message in messages:
        if message["role"] == "user":
            text = (message.get("content") or "").split("\n\n[Attached", 1)[0]
            return " ".join(text.split())[:60] or "(empty)"
    return "(empty)"


class Session:
    def __init__(self, directory=None, session_id=None):
        self.directory = Path(directory) if directory else sessions_dir()
        self.id = session_id or _new_id()
        self.written = 0  # messages already on disk

    @property
    def path(self):
        return self.directory / f"{self.id}.jsonl"

    def _append(self, entries):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save(self, messages):
        """Append the messages that are not on disk yet."""
        if len(messages) > self.written:
            self._append(messages[self.written:])
            self.written = len(messages)

    def rewind_to(self, count):
        self._append([{"rewind_to": count}])
        self.written = count

    def replace(self, messages):
        self._append([{"replace": messages}])
        self.written = len(messages)

    def start_new(self):
        """Continue in a fresh file; the old chat stays listed."""
        self.id = _new_id()
        self.written = 0

    def open(self, session_id):
        """Switch to a saved session and return its messages."""
        self.id = session_id
        messages = load(self.path)
        self.written = len(messages)
        return messages

    def list(self):
        """Saved sessions for this project, newest first."""
        if not self.directory.is_dir():
            return []
        files = sorted(self.directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for path in files:
            messages = load(path)
            result.append({"id": path.stem, "title": title(messages), "messages": len(messages)})
        return result


def preview(messages, limit=10):
    """The last `limit` exchanges of a transcript as short lines, for the
    screen after a session is opened or resumed."""
    lines = []
    for message in messages[1:]:
        content = " ".join((message.get("content") or "").split())
        if message["role"] == "user":
            if content.startswith("<summary>"):
                lines.append("  (earlier conversation compacted)")
            else:
                lines.append(f"  you > {title([message])}")
        elif message["role"] == "assistant":
            for call in message.get("tool_calls") or []:
                lines.append(f"    → {call['function']['name']}")
            if content:
                lines.append(f"  agent > {content[:100]}")
    return "\n".join(lines[-limit * 3:])
