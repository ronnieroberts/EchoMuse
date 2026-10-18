"""
Tests for em_timer_ring: the LED ring's timer countdown.

Written from the geometry the module documents: 12 LEDs, one per five minutes
of an hour, clockwise from 12 o'clock, the leading LED brightest.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import em_timer_ring as ring
from em_timer_ring import RingStyle, RingTimer, countdown_frame

MIN = 60.0
HOUR = 3600.0
STYLE = RingStyle()


def lit(frame):
    """Indices of LEDs that show any light."""
    return [i for i, c in enumerate(frame) if sum(c) > 0]


def strength(frame, i):
    """Green channel as a proxy for strength with the default main colour."""
    return frame[i][1]


def frame_for(*remaining_s, **kw):
    return countdown_frame([RingTimer(r) for r in remaining_s], STYLE, **kw)


def test_no_timers_is_dark():
    assert frame_for() == [(0, 0, 0)] * 12


def test_finished_timer_is_not_drawn():
    assert frame_for(0) == [(0, 0, 0)] * 12


def test_forty_five_minutes_ends_on_the_led_at_nine_oclock():
    f = frame_for(45 * MIN)
    assert lit(f) == list(range(10))        # LEDs 0 (12 o'clock) to 9 (9 o'clock)


def test_leading_led_is_brightest_and_body_is_flat():
    f = frame_for(45 * MIN)
    body = {strength(f, i) for i in range(9)}
    assert len(body) == 1
    assert strength(f, 9) > max(body)


def test_leading_point_slides_between_leds_as_time_drains():
    # 44 minutes is between the LEDs at 8 and 9 o'clock, nearer the one at 9.
    f = frame_for(44 * MIN)
    assert strength(f, 9) > strength(f, 8)
    # 41 minutes is nearer the one at 8 o'clock: the lead has moved down.
    g = frame_for(41 * MIN)
    assert strength(g, 8) > strength(g, 9)


def test_each_minute_changes_the_ring():
    seen = {tuple(frame_for(m * MIN)) for m in range(10, 21)}
    assert len(seen) == 11
    assert len({tuple(frame_for(m * MIN)) for m in range(2, 6)}) == 4


def test_arc_drains_toward_twelve():
    assert len(lit(frame_for(30 * MIN))) > len(lit(frame_for(20 * MIN))) > len(lit(frame_for(10 * MIN)))
    assert lit(frame_for(10 * MIN))[0] == 0
    assert lit(frame_for(5 * MIN)) == [0, 1]    # the last five minutes: the lead is on LED 1


def test_one_hour_fills_the_ring():
    f = frame_for(60 * MIN)
    assert lit(f) == list(range(12))
    assert strength(f, 0) > strength(f, 11)     # the lead has come round to 12


def test_seventy_five_minutes_is_full_ring_with_marker_on_the_led_at_three_oclock():
    f = frame_for(75 * MIN)
    assert lit(f) == list(range(12))
    assert max(range(12), key=lambda i: strength(f, i)) == 3
    assert sorted(strength(f, i) for i in range(12))[-2] < strength(f, 3)


def test_marker_walks_back_toward_twelve_and_then_drops_to_minutes():
    def marker(m):
        f = frame_for(m * MIN)
        return max(range(12), key=lambda i: strength(f, i))
    assert marker(90) == 6        # 30 minutes past the hour: 6 o'clock
    assert marker(105) == 9
    assert marker(65) == 1        # 5 minutes past: one LED after 12
    assert lit(frame_for(59 * MIN)) == list(range(12))  # minutes arc, nearly full


def test_extra_hours_brighten_the_body_and_cap():
    one = frame_for(75 * MIN)
    two = frame_for(135 * MIN)
    far = frame_for(10 * HOUR + 15 * MIN)
    farther = frame_for(11 * HOUR + 15 * MIN)
    assert strength(two, 8) > strength(one, 8)
    assert strength(far, 8) == strength(farther, 8)   # capped


def test_hour_boundary_marker_is_at_twelve():
    f = frame_for(2 * HOUR)
    assert lit(f) == list(range(12))
    assert max(range(12), key=lambda i: strength(f, i)) == 0


def test_last_minute_uses_a_sixty_second_dial():
    f = frame_for(30)          # 30 seconds left: half the dial, ending at 6 o'clock
    assert lit(f) == list(range(7))
    assert max(range(12), key=lambda i: strength(f, i)) == 6
    assert lit(frame_for(10)) == list(range(3))   # 10 seconds: LEDs at 12, 1 and 2


def test_last_minute_zoom_can_be_turned_off():
    off = countdown_frame([RingTimer(30)], RingStyle(final_zoom_s=0, finale=False))
    # Without the zoom, 30 seconds is a sliver of the hour dial.
    assert lit(off) == [0, 1] and strength(off, 0) > strength(off, 1)


def test_final_second_is_one_revolution():
    start = lit(frame_for(1.0))
    quarter = lit(frame_for(0.75))
    half = lit(frame_for(0.5))
    assert start != half
    # A single dot (two neighbouring LEDs at most) travelling clockwise.
    assert len(half) <= 2 and len(quarter) <= 2
    assert min(half) > min(quarter) or (min(quarter), min(half)) == (0, 5)


def test_finale_can_be_turned_off():
    f = countdown_frame([RingTimer(0.5)], RingStyle(finale=False))
    assert lit(f) == [0, 1]    # the seconds dial's last sliver, not a sweeping dot
    assert lit(frame_for(0.5)) == [0, 6] or len(lit(frame_for(0.5))) <= 2


def test_soonest_timer_is_in_front_in_the_main_colour():
    f = frame_for(20 * MIN, 50 * MIN)
    for i in range(5):                           # the front arc: 12 to 4 o'clock
        assert f[i][1] > f[i][0]                 # green-dominant: main colour
    # Beyond the front timer's arc, the second timer shows in its colour.
    for i in range(5, 11):
        assert f[i][0] > f[i][1]                 # magenta-dominant: second colour


def test_back_timers_are_dimmer_than_the_front_one():
    f = frame_for(20 * MIN, 50 * MIN)
    assert max(f[4]) > max(f[7])


def test_order_of_input_does_not_matter():
    a = countdown_frame([RingTimer(20 * MIN), RingTimer(50 * MIN)], STYLE)
    b = countdown_frame([RingTimer(50 * MIN), RingTimer(20 * MIN)], STYLE)
    assert a == b


def test_muted_keeps_the_ring_red_and_shows_a_white_dot():
    f = frame_for(45 * MIN, muted=True)
    assert all(c[0] >= ring.MUTE_DIM[0] for c in f)           # every LED at least dim red
    whites = [i for i, c in enumerate(f) if c[1] > 0 and c[2] > 0]
    assert 1 <= len(whites) <= 2
    # 45 minutes = 270 degrees = 9 o'clock = exactly the LED at 9.
    assert whites == [9]


def test_muted_with_no_timer_is_dark():
    # The countdown draws nothing; the device's own mute ring is not its job.
    assert countdown_frame([], STYLE, muted=True) == [(0, 0, 0)] * 12


def test_muted_dot_moves_with_the_timer():
    early = [i for i, c in enumerate(frame_for(50 * MIN, muted=True)) if c[1] > 0]
    late = [i for i, c in enumerate(frame_for(10 * MIN, muted=True)) if c[1] > 0]
    assert early != late


def test_no_colour_uses_a_reserved_hue():
    # Red mute, orange link, cyan volume and the amber alarm are taken.
    def reserved(c):
        r, g, b = c
        return (r > 150 and g < 60 and b < 60) or (r > 200 and 100 < g < 200 and b < 60) \
            or (r < 60 and g > 150 and b > 150)
    for c in (STYLE.main, STYLE.second):
        assert not reserved(c)


@pytest.mark.parametrize("remaining", [0.2, 1, 59, 61, 600, 3599, 3600, 3601, 7200, 90000])
def test_frames_are_always_twelve_valid_rgb(remaining):
    for muted in (False, True):
        f = frame_for(remaining, 5000, muted=muted)
        assert len(f) == 12
        for c in f:
            assert len(c) == 3 and all(0 <= v <= 255 and isinstance(v, int) for v in c)


def test_dial_modes():
    assert ring.dial_for(0, STYLE).mode == "done"
    assert ring.dial_for(0.5, STYLE).mode == "finale"
    assert ring.dial_for(30, STYLE).mode == "seconds"
    assert ring.dial_for(30 * MIN, STYLE).mode == "minutes"
    assert ring.dial_for(61 * MIN, STYLE).mode == "hours"
    assert ring.dial_for(61 * MIN, STYLE).wraps == 1
    assert ring.dial_for(2 * HOUR, STYLE).wraps == 1
    assert ring.dial_for(2 * HOUR + 1, STYLE).wraps == 2


def test_rotate_to_hardware():
    frame = [(i + 1, 0, 0) for i in range(12)]
    same = ring.rotate_to_hardware(frame, 0)
    assert same == frame
    shifted = ring.rotate_to_hardware(frame, 3)
    assert shifted[3] == frame[0] and shifted[2] == frame[11]
    backwards = ring.rotate_to_hardware(frame, 3, clockwise=False)
    assert backwards[3] == frame[0] and backwards[2] == frame[1]


def test_a_back_timer_glow_is_as_visible_as_the_front_ones():
    # Scaling the back timer's glow by `behind` on top of an already dim body left
    # it near 5% and invisible on a real Dot (2026-10-18). The glow must match.
    f = frame_for(15 * MIN, 45 * MIN)
    front_glow = max(f[1])                       # 12 to 3 o'clock, front timer
    back_glow = max(f[5])                        # 4 to 8 o'clock, back timer
    assert back_glow >= 0.8 * front_glow


def test_a_back_timer_leading_point_is_a_saturated_second_colour():
    f = frame_for(15 * MIN, 45 * MIN)
    r, g, b = f[9]                               # the 45 minute lead, 9 o'clock
    assert r > g and b > g                       # magenta, not pinkish white
    assert min(r, b) > 150                       # and bright


def test_the_front_leading_point_is_pulled_toward_white():
    f = frame_for(15 * MIN, 45 * MIN)
    r, g, b = f[3]                               # the 15 minute lead, 3 o'clock
    assert g == 255 and r > 150 and b > 150


def test_a_single_timer_glow_is_dim_next_to_its_lead():
    f = frame_for(45 * MIN)
    assert max(f[0]) < 0.2 * max(f[9])
