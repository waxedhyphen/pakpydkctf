"""Bounded, Tk-independent model for AVM2 Graphics command streams."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

MAX_GRAPHICS_COMMANDS = 10_000
MAX_GRAPHICS_PRIMITIVES = 2_048
MAX_GRAPHICS_COORDINATE = 1_000_000.0
MAX_CURVE_SEGMENTS = 96


@dataclass(frozen=True)
class FillStyle:
    kind: str
    color: int = 0
    alpha: float = 1.0
    colors: tuple[int, ...] = ()
    alphas: tuple[float, ...] = ()
    ratios: tuple[int, ...] = ()
    matrix: tuple[float, float, float, float, float, float] | None = None
    spread: str = "pad"
    interpolation: str = "rgb"
    focal: float = 0.0


@dataclass(frozen=True)
class LineStyle:
    thickness: float = 0.0
    color: int = 0
    alpha: float = 1.0
    pixel_hinting: bool = False
    scale_mode: str = "normal"
    caps: str = "round"
    joints: str = "round"
    miter_limit: float = 3.0


@dataclass(frozen=True)
class GraphicsPrimitive:
    commands: tuple[tuple, ...]
    fill: FillStyle | None
    line: LineStyle | None


@dataclass
class GraphicsState:
    primitives: list[GraphicsPrimitive] = field(default_factory=list)
    current_commands: list[tuple] = field(default_factory=list)
    fill: FillStyle | None = None
    line: LineStyle | None = None
    pen_x: float = 0.0
    pen_y: float = 0.0
    command_count: int = 0
    revision: int = 0
    rejected: int = 0

    def touch(self) -> None:
        self.revision += 1


def _number(value, default=0.0):
    try:
        value = float(value)
    except Exception:
        value = float(default)
    if not math.isfinite(value):
        value = float(default)
    return max(-MAX_GRAPHICS_COORDINATE, min(MAX_GRAPHICS_COORDINATE, value))


def _alpha(value):
    return max(0.0, min(1.0, _number(value, 1.0)))


def _color(value):
    try:
        return int(value) & 0xFFFFFF
    except Exception:
        return 0


def _can_add(state: GraphicsState, amount=1) -> bool:
    if state.command_count + amount > MAX_GRAPHICS_COMMANDS:
        state.rejected += 1
        return False
    return True


def _seal(state: GraphicsState) -> bool:
    if not state.current_commands:
        return False
    if len(state.primitives) >= MAX_GRAPHICS_PRIMITIVES:
        state.current_commands.clear()
        state.rejected += 1
        state.touch()
        return False
    state.primitives.append(
        GraphicsPrimitive(tuple(state.current_commands), state.fill, state.line)
    )
    state.current_commands.clear()
    state.touch()
    return True


def clear(state: GraphicsState) -> None:
    state.primitives.clear()
    state.current_commands.clear()
    state.fill = None
    state.line = None
    state.pen_x = state.pen_y = 0.0
    state.command_count = 0
    state.touch()


def begin_fill(state: GraphicsState, color=0, alpha=1.0) -> None:
    _seal(state)
    state.fill = FillStyle("solid", _color(color), _alpha(alpha))
    state.touch()


def begin_gradient_fill(
    state: GraphicsState,
    gradient_type,
    colors,
    alphas,
    ratios,
    matrix=None,
    spread="pad",
    interpolation="rgb",
    focal=0.0,
) -> None:
    _seal(state)
    kind = str(gradient_type or "linear").lower()
    if kind not in ("linear", "radial"):
        kind = "linear"
    color_values = tuple(_color(value) for value in tuple(colors or ())[:15])
    alpha_values = tuple(_alpha(value) for value in tuple(alphas or ())[:15])
    ratio_values = tuple(max(0, min(255, int(value))) for value in tuple(ratios or ())[:15])
    count = min(len(color_values), len(alpha_values), len(ratio_values))
    if count <= 0:
        state.fill = None
    else:
        state.fill = FillStyle(
            "focal" if kind == "radial" and abs(_number(focal)) > 1e-9 else kind,
            colors=color_values[:count],
            alphas=alpha_values[:count],
            ratios=ratio_values[:count],
            matrix=tuple(matrix) if matrix is not None else None,
            spread=str(spread or "pad").lower(),
            interpolation=str(interpolation or "rgb").lower(),
            focal=max(-0.99, min(0.99, _number(focal))),
        )
    state.touch()


def end_fill(state: GraphicsState) -> None:
    _seal(state)
    state.fill = None
    state.touch()


def line_style(
    state: GraphicsState,
    thickness=None,
    color=0,
    alpha=1.0,
    pixel_hinting=False,
    scale_mode="normal",
    caps="round",
    joints="round",
    miter_limit=3.0,
) -> None:
    _seal(state)
    if thickness is None:
        state.line = None
    else:
        width = max(0.0, min(4096.0, _number(thickness)))
        state.line = None if width <= 0.0 else LineStyle(
            width, _color(color), _alpha(alpha), bool(pixel_hinting),
            str(scale_mode or "normal"), str(caps or "round"),
            str(joints or "round"), max(1.0, min(255.0, _number(miter_limit, 3.0))),
        )
    state.touch()


def move_to(state: GraphicsState, x, y) -> None:
    if not _can_add(state):
        return
    state.pen_x, state.pen_y = _number(x), _number(y)
    state.current_commands.append(("M", state.pen_x, state.pen_y))
    state.command_count += 1
    state.touch()


def _ensure_start(state: GraphicsState) -> None:
    if not state.current_commands:
        state.current_commands.append(("M", state.pen_x, state.pen_y))
        state.command_count += 1


def line_to(state: GraphicsState, x, y) -> None:
    if not _can_add(state, 2 if not state.current_commands else 1):
        return
    _ensure_start(state)
    state.pen_x, state.pen_y = _number(x), _number(y)
    state.current_commands.append(("L", state.pen_x, state.pen_y))
    state.command_count += 1
    state.touch()


def curve_to(state: GraphicsState, cx, cy, ax, ay) -> None:
    if not _can_add(state, 2 if not state.current_commands else 1):
        return
    _ensure_start(state)
    command = ("Q", _number(cx), _number(cy), _number(ax), _number(ay))
    state.current_commands.append(command)
    state.pen_x, state.pen_y = command[-2], command[-1]
    state.command_count += 1
    state.touch()


def cubic_curve_to(state: GraphicsState, c1x, c1y, c2x, c2y, ax, ay) -> None:
    if not _can_add(state, 2 if not state.current_commands else 1):
        return
    _ensure_start(state)
    command = (
        "C", _number(c1x), _number(c1y), _number(c2x), _number(c2y),
        _number(ax), _number(ay),
    )
    state.current_commands.append(command)
    state.pen_x, state.pen_y = command[-2], command[-1]
    state.command_count += 1
    state.touch()


def _append_closed(state: GraphicsState, commands) -> None:
    _seal(state)
    commands = tuple(commands)
    if not _can_add(state, len(commands)):
        return
    if len(state.primitives) >= MAX_GRAPHICS_PRIMITIVES:
        state.rejected += 1
        return
    state.primitives.append(GraphicsPrimitive(commands, state.fill, state.line))
    state.command_count += len(commands)
    state.touch()


def draw_rect(state: GraphicsState, x, y, width, height) -> None:
    x, y = _number(x), _number(y)
    width, height = _number(width), _number(height)
    x2, y2 = x + width, y + height
    _append_closed(state, (
        ("M", x, y), ("L", x2, y), ("L", x2, y2), ("L", x, y2), ("Z",),
    ))


def draw_round_rect(state: GraphicsState, x, y, width, height, ellipse_width, ellipse_height=None) -> None:
    x, y = _number(x), _number(y)
    width, height = _number(width), _number(height)
    ew = abs(_number(ellipse_width))
    eh = ew if ellipse_height is None else abs(_number(ellipse_height))
    rx = min(abs(width) / 2.0, ew / 2.0)
    ry = min(abs(height) / 2.0, eh / 2.0)
    x2, y2 = x + width, y + height
    left, right = min(x, x2), max(x, x2)
    top, bottom = min(y, y2), max(y, y2)
    k = 0.5522847498307936
    _append_closed(state, (
        ("M", left + rx, top),
        ("L", right - rx, top),
        ("C", right - rx + rx * k, top, right, top + ry - ry * k, right, top + ry),
        ("L", right, bottom - ry),
        ("C", right, bottom - ry + ry * k, right - rx + rx * k, bottom, right - rx, bottom),
        ("L", left + rx, bottom),
        ("C", left + rx - rx * k, bottom, left, bottom - ry + ry * k, left, bottom - ry),
        ("L", left, top + ry),
        ("C", left, top + ry - ry * k, left + rx - rx * k, top, left + rx, top),
        ("Z",),
    ))


def draw_ellipse(state: GraphicsState, x, y, width, height) -> None:
    x, y = _number(x), _number(y)
    width, height = _number(width), _number(height)
    cx, cy = x + width / 2.0, y + height / 2.0
    rx, ry = abs(width) / 2.0, abs(height) / 2.0
    k = 0.5522847498307936
    _append_closed(state, (
        ("M", cx + rx, cy),
        ("C", cx + rx, cy + ry * k, cx + rx * k, cy + ry, cx, cy + ry),
        ("C", cx - rx * k, cy + ry, cx - rx, cy + ry * k, cx - rx, cy),
        ("C", cx - rx, cy - ry * k, cx - rx * k, cy - ry, cx, cy - ry),
        ("C", cx + rx * k, cy - ry, cx + rx, cy - ry * k, cx + rx, cy),
        ("Z",),
    ))


def draw_circle(state: GraphicsState, x, y, radius) -> None:
    radius = abs(_number(radius))
    draw_ellipse(state, _number(x) - radius, _number(y) - radius, radius * 2.0, radius * 2.0)


def seal(state: GraphicsState) -> None:
    _seal(state)


def _curve_steps(points) -> int:
    length = 0.0
    for left, right in zip(points, points[1:]):
        length += math.hypot(right[0] - left[0], right[1] - left[1])
    return max(3, min(MAX_CURVE_SEGMENTS, int(math.ceil(length / 5.0))))


def flatten_primitive(primitive: GraphicsPrimitive):
    contours = []
    current = []
    closed = False
    start = None
    point = (0.0, 0.0)

    def finish():
        nonlocal current, closed, start
        if current:
            contours.append((tuple(current), bool(closed)))
        current = []
        closed = False
        start = None

    for command in primitive.commands:
        kind = command[0]
        if kind == "M":
            finish()
            point = (float(command[1]), float(command[2]))
            current = [point]
            start = point
        elif kind == "L":
            if not current:
                current = [point]
                start = point
            point = (float(command[1]), float(command[2]))
            current.append(point)
        elif kind == "Q":
            if not current:
                current = [point]
                start = point
            p0 = point
            control = (float(command[1]), float(command[2]))
            p1 = (float(command[3]), float(command[4]))
            steps = _curve_steps((p0, control, p1))
            for index in range(1, steps + 1):
                t = index / float(steps)
                inv = 1.0 - t
                current.append((
                    inv * inv * p0[0] + 2.0 * inv * t * control[0] + t * t * p1[0],
                    inv * inv * p0[1] + 2.0 * inv * t * control[1] + t * t * p1[1],
                ))
            point = p1
        elif kind == "C":
            if not current:
                current = [point]
                start = point
            p0 = point
            c1 = (float(command[1]), float(command[2]))
            c2 = (float(command[3]), float(command[4]))
            p1 = (float(command[5]), float(command[6]))
            steps = _curve_steps((p0, c1, c2, p1))
            for index in range(1, steps + 1):
                t = index / float(steps)
                inv = 1.0 - t
                current.append((
                    inv ** 3 * p0[0] + 3 * inv * inv * t * c1[0]
                    + 3 * inv * t * t * c2[0] + t ** 3 * p1[0],
                    inv ** 3 * p0[1] + 3 * inv * inv * t * c1[1]
                    + 3 * inv * t * t * c2[1] + t ** 3 * p1[1],
                ))
            point = p1
        elif kind == "Z":
            if current and start is not None and current[-1] != start:
                current.append(start)
            point = start or point
            closed = True
            finish()
    finish()
    return tuple(contours)


def state_bounds(state: GraphicsState):
    seal(state)
    left = top = math.inf
    right = bottom = -math.inf
    max_line = 0.0
    for primitive in state.primitives:
        if primitive.line is not None:
            max_line = max(max_line, primitive.line.thickness)
        for points, _closed in flatten_primitive(primitive):
            for x, y in points:
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
    if not math.isfinite(left):
        return None
    pad = max(1.0, max_line * 0.5 + 1.0)
    return (left - pad, top - pad, right + pad, bottom + pad)
