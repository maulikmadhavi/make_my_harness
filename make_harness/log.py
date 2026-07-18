"""JSONL run log: one file per session, one event per line.

Every LLM request/response, tool call/result, permission verdict, and error
goes through RunLog.event(), so a session can be fully replayed from its file.
"""

import json
import time
import uuid
from pathlib import Path


class RunLog:
    def __init__(self, log_dir="logs"):
        self.run_id = uuid.uuid4().hex[:8]
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = Path(log_dir) / f"{stamp}_{self.run_id}.jsonl"
        self.path.parent.mkdir(exist_ok=True)

    def event(self, kind, **data):
        record = {"ts": round(time.time(), 3), "run": self.run_id, "kind": kind, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
