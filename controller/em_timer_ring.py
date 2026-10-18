"""
em_timer_ring.py — the LED ring's timer countdown (pure logic)
==============================================================

Draws running timers on the Echo's 12-LED ring, the way a clock face would.
Pure: timers and a style go in, twelve RGB triples come out, so the controller
test suite imports it without pulling in aiohttp/openwakeword, and the web
simulator (tools/ring_sim) renders the exact same frames the Echo would.

Geometry
--------
The ring is read like a clock: 12 o'clock is the top, the arc grows clockwise,
and the 12 LEDs sit on the hour marks, 30 degrees apart. Frames are in DIAL
order: index 0 is the LED at 12 o'clock and the numbers run clockwise. Which
physical LED that is belongs to the board, so the caller rotates the frame onto
the hardware (see `rotate_to_hardware`). On the Echo Dot 2 (biscuit), measured
on a Kitchen Dot 2026-10-18, hardware LED 0 is at 8 o'clock and the indices run
clockwise, so the LED at 12 o'clock is hardware LED 4.

Dial scales, chosen by how long a timer has left:

  * Under an hour: the dial is 60 minutes, so one LED is 5 minutes. The arc
    runs from 12 clockwise to the time left and drains back toward 12, ending
    on the LED at that position (45 minutes ends on the LED at 9 o'clock). The
    leading LED is the brightest and fades out as the time drains toward the
    next one down, so the ring changes every minute, not every five.
  * An hour or more: the ring is full and gets slightly brighter for every
    extra hour, and a bright marker shows the minutes past the last whole hour
    (75 minutes: full ring, marker on the LED at 3 o'clock). Crossing the top hands back
    to the minutes arc.
  * The last minute: the dial is 60 seconds, so one LED is 5 seconds and the
    arc sweeps back to 12 like a second hand. (Optional: `final_zoom_s`.)
  * The last second: one bright dot makes a full revolution. (Optional:
    `finale`.)

Several timers: the one with the least time left is drawn in front, in the main
colour and at full strength. The others are drawn behind it, dimmer, in the
second colour.

Muted: the countdown must not hide that the microphone is off, so the ring
stays dim red and only a white dot — the front timer's position — moves over
it. See `countdown_frame(..., muted=True)`.

Colours avoid the ones the ring already means something by: red (mute),
orange (controller unreachable), cyan (volume) and amber (a timer ringing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

LED_COUNT = 12
SLOT_DEG = 360.0 / LED_COUNT

Rgb = tuple[int, int, int]

SECONDS_PER_DIAL_HOUR = 3600.0
SECONDS_PER_DIAL_MINUTE = 60.0

# The ring when muted (the same family as the device's own solid red) and the
# dot that moves over it.
MUTE_DIM: Rgb = (60, 0, 0)
MUTE_DOT: Rgb = (255, 255, 255)


@dataclass(frozen=True)
class RingTimer:
    """One running timer. `remaining_s` is what the caller computed from the
    event's seconds_left and when it arrived; this module never reads a clock."""

    remaining_s: float
    timer_id: str = ""


@dataclass(frozen=True)
class RingStyle:
    """Look of the countdown. Colours are full-strength; the levels scale them."""

    main: Rgb = (60, 255, 80)
    second: Rgb = (255, 60, 220)
    body: float = 0.12          # lit LEDs behind the leading edge: a quiet glow
    head: float = 1.00          # the leading point, and the hour marker
    head_white: float = 0.65    # how far the leading point is pulled toward white
    behind: float = 1.00        # leading-point strength of every timer but the front one
    behind_white: float = 0.15  # how far their leading point is pulled toward white
    wrap_step: float = 0.04     # extra body brightness per whole hour
    wrap_cap: float = 0.16      # ceiling on the extra
    final_zoom_s: float = 60.0  # dial becomes seconds below this; 0 turns it off
    finale: bool = True         # one full revolution in the last second
    finale_s: float = 1.0


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _scale(c: Rgb, f: float) -> Rgb:
    f = _clamp01(f)
    return (round(c[0] * f), round(c[1] * f), round(c[2] * f))


def _add(a: Rgb, b: Rgb) -> Rgb:
    return (min(255, a[0] + b[0]), min(255, a[1] + b[1]), min(255, a[2] + b[2]))


def _dot_weights(angle_deg: float) -> list[float]:
    """Spread a point at `angle_deg` (clockwise from 12) over the two LEDs it
    sits between, so it moves smoothly around a ring of twelve. LED i is at
    30*i degrees, so a point on an hour mark lights exactly one LED."""
    w = [0.0] * LED_COUNT
    pos = (angle_deg % 360.0) / SLOT_DEG
    lo = int(pos // 1)
    frac = pos - lo
    w[lo % LED_COUNT] += 1.0 - frac
    w[(lo + 1) % LED_COUNT] += frac
    return w


def _arc_levels(angle_deg: float, body: float, head: float) -> list[tuple[float, float]]:
    """(body, head) strength of each LED for an arc from 12 o'clock clockwise
    to the angle.

    Every LED short of the leading edge glows at `body`. The leading edge is a
    bright point between two LEDs: on an hour mark it is one LED at full
    strength (45 minutes ends on the LED at 9 o'clock), and between marks it is
    shared by the two either side, so the point slides smoothly toward 12 as
    the timer drains and the ring changes every minute.
    """
    angle = max(0.0, min(360.0, angle_deg))
    lead = int(angle // SLOT_DEG)
    return [(body if i < lead else 0.0, head * w)
            for i, w in enumerate(_dot_weights(angle))]


@dataclass(frozen=True)
class Dial:
    """What the dial is showing for one timer."""

    mode: str                  # "minutes" | "hours" | "seconds" | "finale" | "done"
    angle_deg: float           # position of the leading edge / marker
    wraps: int = 0             # whole hours above the first


def dial_for(remaining_s: float, style: RingStyle) -> Dial:
    """Pick the scale and the leading-edge angle for a timer."""
    if remaining_s <= 0:
        return Dial("done", 0.0)
    if style.finale and remaining_s <= style.finale_s:
        # One revolution across the last second, clockwise from 12.
        return Dial("finale", (1.0 - remaining_s / style.finale_s) * 360.0)
    if style.final_zoom_s > 0 and remaining_s <= style.final_zoom_s:
        return Dial("seconds", remaining_s / style.final_zoom_s * 360.0)
    if remaining_s <= SECONDS_PER_DIAL_HOUR:
        return Dial("minutes", remaining_s / SECONDS_PER_DIAL_HOUR * 360.0)
    wraps = int((remaining_s - 1e-9) // SECONDS_PER_DIAL_HOUR)
    rest = remaining_s - wraps * SECONDS_PER_DIAL_HOUR
    return Dial("hours", rest / SECONDS_PER_DIAL_HOUR * 360.0, wraps)


def _levels(dial: Dial, style: RingStyle) -> list[tuple[float, float]]:
    """Per-LED (body, head) strength (0..1) for one timer, before colour."""
    if dial.mode == "done":
        return [(0.0, 0.0)] * LED_COUNT
    if dial.mode == "finale":
        # A single dot; the trail is not drawn so it reads as one sweep.
        return [(0.0, style.head * w) for w in _dot_weights(dial.angle_deg)]
    if dial.mode == "hours":
        # The ring is full and glows a little more for every extra hour; the
        # marker shows the minutes past the last whole hour.
        base = style.body + min(style.wrap_cap, dial.wraps * style.wrap_step)
        return [(base, style.head * w) for w in _dot_weights(dial.angle_deg)]
    return _arc_levels(dial.angle_deg, style.body, style.head)


def _mix(a: Rgb, b: Rgb, t: float) -> Rgb:
    t = _clamp01(t)
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t),
            round(a[2] + (b[2] - a[2]) * t))


WHITE: Rgb = (255, 255, 255)


def _paint(levels: Sequence[tuple[float, float]], colour: Rgb, style: RingStyle,
           head_strength: float = 1.0, head_white: float | None = None) -> list[Rgb]:
    """Colour a timer's levels: the body in the timer's colour, the leading
    point pulled toward white so it stands out against the glow. A timer behind
    keeps its body as visible as the front one's and only its leading point is
    held back: scaling the body as well left it at about 5% and invisible."""
    head_colour = _mix(colour, WHITE, style.head_white if head_white is None else head_white)
    out = []
    for body, head in levels:
        b, h = _scale(colour, body), _scale(head_colour, head * head_strength)
        out.append((max(b[0], h[0]), max(b[1], h[1]), max(b[2], h[2])))
    return out


def countdown_frame(
    timers: Sequence[RingTimer],
    style: RingStyle | None = None,
    muted: bool = False,
) -> list[Rgb]:
    """The 12 LED colours, in dial order, for the timers currently running.

    Returns all-off when there is nothing to show. The soonest timer is the
    front one; any others are drawn behind it.
    """
    style = style or RingStyle()
    running = sorted((t for t in timers if t.remaining_s > 0),
                     key=lambda t: t.remaining_s)
    if not running:
        return [(0, 0, 0)] * LED_COUNT

    front = running[0]
    if muted:
        dot = _dot_weights(dial_for(front.remaining_s, style).angle_deg)
        return [_add(MUTE_DIM, _scale(MUTE_DOT, w)) for w in dot]

    frame = [(0, 0, 0)] * LED_COUNT
    for t in reversed(running[1:]):
        levels = _levels(dial_for(t.remaining_s, style), style)
        layer = _paint(levels, style.second, style, style.behind, style.behind_white)
        # Nearer timers paint over farther ones where they have any light.
        frame = [new if sum(new) > 0 else old for new, old in zip(layer, frame)]
    levels = _levels(dial_for(front.remaining_s, style), style)
    top = _paint(levels, style.main, style)
    return [new if sum(new) > 0 else old for new, old in zip(top, frame)]


def rotate_to_hardware(frame: Sequence[Rgb], led_at_twelve: int,
                       clockwise: bool = True) -> list[Rgb]:
    """Map a dial-order frame onto the board's LED indices.

    `led_at_twelve` is the hardware index of the LED that starts the dial (the
    first one clockwise of 12 o'clock); `clockwise` says whether increasing
    hardware indices run clockwise. Both are measured per board, not guessed.
    """
    out: list[Rgb] = [(0, 0, 0)] * LED_COUNT
    for slot, colour in enumerate(frame):
        step = slot if clockwise else -slot
        out[(led_at_twelve + step) % LED_COUNT] = colour
    return out
