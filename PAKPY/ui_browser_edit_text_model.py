"""Pure bounded text-editing model used by the UI Browser input patch.

The model has no Tk, renderer or AVM2 dependencies.  It implements selection,
replacement, movement, undo/redo and the conservative subset of Flash's
``TextField.restrict`` syntax used by the preview runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


MAX_TEXT_CHARS = 1_000_000
MAX_CLIPBOARD_CHARS = 65_536
MAX_UNDO_STEPS = 100
MAX_RESTRICT_PATTERN = 1_024


@dataclass(frozen=True)
class EditableTarget:
    path: str
    text: str
    multiline: bool = False
    selectable: bool = True
    max_chars: int = 0
    restrict: str = ""
    password: bool = False
    dynamic: bool = False
    variable_name: str = ""

    @property
    def bounded_max_chars(self) -> int:
        value = int(self.max_chars or 0)
        if value <= 0:
            return MAX_TEXT_CHARS
        return max(0, min(MAX_TEXT_CHARS, value))


@dataclass
class EditSnapshot:
    text: str
    anchor: int
    caret: int


@dataclass
class EditSession:
    path: str
    original_text: str
    text: str
    anchor: int = 0
    caret: int = 0
    dragging: bool = False
    active: bool = True
    undo: list[EditSnapshot] = field(default_factory=list)
    redo: list[EditSnapshot] = field(default_factory=list)

    def clamp(self) -> None:
        self.anchor = clamp_index(self.text, self.anchor)
        self.caret = clamp_index(self.text, self.caret)

    @property
    def selection(self) -> tuple[int, int]:
        return normalized_selection(self.anchor, self.caret, len(self.text))

    @property
    def selected_text(self) -> str:
        start, end = self.selection
        return self.text[start:end]

    def snapshot(self) -> EditSnapshot:
        return EditSnapshot(self.text, self.anchor, self.caret)

    def restore(self, value: EditSnapshot) -> None:
        self.text = str(value.text)
        self.anchor = int(value.anchor)
        self.caret = int(value.caret)
        self.clamp()

    def push_undo(self) -> None:
        current = self.snapshot()
        if self.undo and self.undo[-1] == current:
            return
        self.undo.append(current)
        del self.undo[:-MAX_UNDO_STEPS]
        self.redo.clear()

    def undo_once(self) -> bool:
        if not self.undo:
            return False
        current = self.snapshot()
        previous = self.undo.pop()
        self.redo.append(current)
        del self.redo[:-MAX_UNDO_STEPS]
        self.restore(previous)
        return True

    def redo_once(self) -> bool:
        if not self.redo:
            return False
        current = self.snapshot()
        following = self.redo.pop()
        self.undo.append(current)
        del self.undo[:-MAX_UNDO_STEPS]
        self.restore(following)
        return True


def clamp_index(text: str, index: int) -> int:
    try:
        value = int(index)
    except Exception:
        value = 0
    return max(0, min(len(str(text)), value))


def normalized_selection(anchor: int, caret: int, length: int) -> tuple[int, int]:
    left = max(0, min(int(length), int(anchor)))
    right = max(0, min(int(length), int(caret)))
    return (left, right) if left <= right else (right, left)


def replace_range(text: str, start: int, end: int, replacement: str,
                  max_chars: int = 0) -> tuple[str, int]:
    text = str(text)
    replacement = str(replacement)
    start, end = normalized_selection(start, end, len(text))
    limit = MAX_TEXT_CHARS if int(max_chars or 0) <= 0 else min(MAX_TEXT_CHARS, int(max_chars))
    available = max(0, limit - (len(text) - (end - start)))
    replacement = replacement[:available]
    result = text[:start] + replacement + text[end:]
    return result, start + len(replacement)


def _parse_restrict(pattern: str):
    """Return ``(negated, predicate)`` for a bounded Flash-like restrict pattern.

    Supported syntax is deliberately small and deterministic: literal characters,
    escaped literals, ranges such as ``A-Z`` and a leading ``^`` for negation.
    Flash's repeated include/exclude groups are not guessed.
    """
    pattern = str(pattern or "")[:MAX_RESTRICT_PATTERN]
    if not pattern:
        return False, None
    negated = pattern.startswith("^")
    if negated:
        pattern = pattern[1:]
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\" and i + 1 < len(pattern):
            tokens.append((pattern[i + 1], pattern[i + 1]))
            i += 2
            continue
        if i + 2 < len(pattern) and pattern[i + 1] == "-":
            end = pattern[i + 2]
            if end == "\\" and i + 3 < len(pattern):
                end = pattern[i + 3]
                i += 1
            left, right = ord(char), ord(end)
            if left > right:
                left, right = right, left
            tokens.append((chr(left), chr(right)))
            i += 3
            continue
        tokens.append((char, char))
        i += 1

    def allowed(value: str) -> bool:
        code = ord(value)
        matched = any(ord(left) <= code <= ord(right) for left, right in tokens)
        return not matched if negated else matched

    return negated, allowed


def filter_restrict(value: str, pattern: str) -> str:
    value = str(value)
    _negated, predicate = _parse_restrict(pattern)
    if predicate is None:
        return value
    return "".join(char for char in value if predicate(char))


def insert_text(session: EditSession, target: EditableTarget, value: str) -> bool:
    value = str(value)
    if not target.multiline:
        value = value.replace("\r", "").replace("\n", "")
    else:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = filter_restrict(value, target.restrict)
    if not value and session.selection[0] == session.selection[1]:
        return False
    session.push_undo()
    start, end = session.selection
    text, caret = replace_range(session.text, start, end, value, target.bounded_max_chars)
    changed = text != session.text
    session.text = text
    session.anchor = session.caret = caret
    session.clamp()
    return changed


def replace_selection(session: EditSession, target: EditableTarget, value: str) -> bool:
    return insert_text(session, target, value)


def replace_text(session: EditSession, target: EditableTarget, start: int,
                 end: int, value: str) -> bool:
    session.anchor = clamp_index(session.text, start)
    session.caret = clamp_index(session.text, end)
    return insert_text(session, target, value)


def select_all(session: EditSession) -> None:
    session.anchor = 0
    session.caret = len(session.text)


def collapse_selection(session: EditSession, toward_end: bool) -> bool:
    start, end = session.selection
    if start == end:
        return False
    session.anchor = session.caret = end if toward_end else start
    return True


def _previous_word(text: str, index: int) -> int:
    index = clamp_index(text, index)
    if index <= 0:
        return 0
    index -= 1
    while index > 0 and text[index].isspace():
        index -= 1
    while index > 0 and not text[index - 1].isspace():
        index -= 1
    return index


def _next_word(text: str, index: int) -> int:
    index = clamp_index(text, index)
    length = len(text)
    while index < length and not text[index].isspace():
        index += 1
    while index < length and text[index].isspace():
        index += 1
    return index


def _line_start(text: str, index: int) -> int:
    index = clamp_index(text, index)
    found = text.rfind("\n", 0, index)
    return found + 1


def _line_end(text: str, index: int) -> int:
    index = clamp_index(text, index)
    found = text.find("\n", index)
    return len(text) if found < 0 else found


def _line_column(text: str, index: int) -> tuple[int, int]:
    start = _line_start(text, index)
    return start, index - start


def _vertical_index(text: str, index: int, delta: int) -> int:
    start, column = _line_column(text, index)
    if delta < 0:
        if start == 0:
            return index
        previous_end = start - 1
        previous_start = _line_start(text, previous_end)
        return min(previous_end, previous_start + column)
    end = _line_end(text, index)
    if end >= len(text):
        return index
    next_start = end + 1
    next_end = _line_end(text, next_start)
    return min(next_end, next_start + column)


def move_caret(session: EditSession, direction: str, extend: bool = False,
               by_word: bool = False) -> bool:
    direction = str(direction)
    old_anchor, old_caret = session.anchor, session.caret
    if not extend and direction in ("left", "right"):
        if collapse_selection(session, direction == "right"):
            return True
    index = session.caret
    if direction == "left":
        index = _previous_word(session.text, index) if by_word else max(0, index - 1)
    elif direction == "right":
        index = _next_word(session.text, index) if by_word else min(len(session.text), index + 1)
    elif direction == "home":
        index = 0 if by_word else _line_start(session.text, index)
    elif direction == "end":
        index = len(session.text) if by_word else _line_end(session.text, index)
    elif direction == "up":
        index = _vertical_index(session.text, index, -1)
    elif direction == "down":
        index = _vertical_index(session.text, index, 1)
    else:
        return False
    session.caret = index
    if not extend:
        session.anchor = index
    session.clamp()
    return (old_anchor, old_caret) != (session.anchor, session.caret)


def delete_backward(session: EditSession, target: EditableTarget,
                    by_word: bool = False) -> bool:
    start, end = session.selection
    if start == end:
        start = _previous_word(session.text, start) if by_word else max(0, start - 1)
    if start == end:
        return False
    session.push_undo()
    session.text, caret = replace_range(session.text, start, end, "", target.bounded_max_chars)
    session.anchor = session.caret = caret
    return True


def delete_forward(session: EditSession, target: EditableTarget,
                   by_word: bool = False) -> bool:
    start, end = session.selection
    if start == end:
        end = _next_word(session.text, end) if by_word else min(len(session.text), end + 1)
    if start == end:
        return False
    session.push_undo()
    session.text, caret = replace_range(session.text, start, end, "", target.bounded_max_chars)
    session.anchor = session.caret = caret
    return True


def display_text(text: str, password: bool) -> str:
    return "•" * len(str(text)) if password else str(text)


def sanitize_clipboard(value: object, multiline: bool) -> str:
    text = str(value or "")[:MAX_CLIPBOARD_CHARS]
    text = text.replace("\x00", "")
    if multiline:
        return text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\r\n]+", " ", text)
