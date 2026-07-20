"""@-mention expansion: `@path` in user input attaches that file or folder.

`Explain @make_harness/llm.py` sends the message text unchanged plus an
attachment block with the file content, so the model sees it immediately
instead of spending a read_file tool call. Folders attach a listing.

Only mentions that resolve to an existing path are expanded — `@gmail.com`
in prose stays plain text. Attachments are capped head+tail so one huge
file can't blow the context on its own.
"""

import re
from pathlib import Path

from make_harness.toolsets import truncate

MAX_CHARS = 20_000
_MENTION = re.compile(r"@([\w./\\:~-]+)")
_TRAILING_PUNCTUATION = ".,;:!?)"


def _resolve(raw):
    """Return (mention_text, Path) for an existing path, else None.

    A mention at the end of a sentence drags punctuation into the regex
    match (`@llm.py.`), so the punctuation-stripped candidate is tried
    first. Stripped-first also keeps behavior identical across platforms:
    Windows itself ignores trailing dots, so checking the raw token first
    would resolve `@a.py.` to a different label than Linux does.
    """
    for candidate in (raw.rstrip(_TRAILING_PUNCTUATION), raw):
        path = Path(candidate).expanduser()
        if candidate and path.exists():
            return candidate, path
    return None


def expand_mentions(text):
    """Expand @path mentions in user input.

    Returns (expanded_text, attached): the text with attachment blocks
    appended, and the list of mention strings that actually resolved.
    """
    blocks = []
    attached = []
    for raw in _MENTION.findall(text):
        resolved = _resolve(raw)
        if resolved is None:
            continue
        mention, path = resolved
        if mention in attached:
            continue
        attached.append(mention)
        if path.is_dir():
            entries = sorted(
                entry.name + ("/" if entry.is_dir() else "") for entry in path.iterdir()
            )
            blocks.append(f"[Attached folder {mention}]\n" + ("\n".join(entries) or "(empty)"))
        else:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                blocks.append(f"[Attachment {mention} could not be read: {e}]")
                continue
            blocks.append(f"[Attached file {mention}]\n{truncate(content, MAX_CHARS)}")
    if not blocks:
        return text, attached
    return text + "\n\n" + "\n\n".join(blocks), attached
