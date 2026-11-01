"""
Tests for double press detection on keys, dials and touch keys.

The detector decides which of short-up, hold-stop and double press a press turns
into; DeckController only forwards those decisions as input events, so the timing
rules are all covered here without a deck.

Run with:

    python3 -m unittest discover -s tests -t .
"""
import threading
import time
import unittest

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.DeckManagement.Subclasses.DoublePressDetector import DoublePressDetector


class ManualTimer:
    """Stand-in for threading.Timer that only fires when the test says so."""
    created: list["ManualTimer"] = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.cancelled = False
        self.started = False
        self.daemon = False
        ManualTimer.created.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.function()


class Recorder:
    def __init__(self):
        self.events: list[str] = []

    def short_up(self):
        self.events.append("short_up")

    def hold_stop(self):
        self.events.append("hold_stop")


class TestDoublePressDetector(unittest.TestCase):
    def setUp(self):
        ManualTimer.created = []
        self.detector = DoublePressDetector(get_window=lambda: 0.3, timer_factory=ManualTimer)
        self.rec = Recorder()

    def press(self, held: bool = False, bound: bool = True) -> bool:
        is_double = self.detector.on_down()
        self.detector.on_release(held=held, double_press_bound=bound,
                                 emit_short_up=self.rec.short_up, emit_hold_stop=self.rec.hold_stop)
        return is_double

    def test_unbound_short_press_is_immediate(self):
        self.assertFalse(self.press(bound=False))
        self.assertEqual(self.rec.events, ["short_up"])
        self.assertEqual(ManualTimer.created, [])

    def test_unbound_presses_never_become_double(self):
        self.assertFalse(self.press(bound=False))
        self.assertFalse(self.press(bound=False))
        self.assertEqual(self.rec.events, ["short_up", "short_up"])

    def test_bound_single_press_sends_short_up_after_window(self):
        self.assertFalse(self.press())
        self.assertEqual(self.rec.events, [])
        timer = ManualTimer.created[0]
        self.assertTrue(timer.started)
        self.assertEqual(timer.interval, 0.3)
        timer.fire()
        self.assertEqual(self.rec.events, ["short_up"])

    def test_second_press_in_window_is_double_and_swallows_short_ups(self):
        self.assertFalse(self.press())
        self.assertTrue(self.press())
        self.assertTrue(ManualTimer.created[0].cancelled)
        ManualTimer.created[0].fire()
        self.assertEqual(self.rec.events, [])
        # Only one timer: the second release must not start another window
        self.assertEqual(len(ManualTimer.created), 1)

    def test_second_press_held_is_still_double_without_hold_stop(self):
        self.press()
        self.assertTrue(self.press(held=True))
        self.assertEqual(self.rec.events, [])

    def test_third_press_starts_fresh(self):
        self.press()
        self.press()
        self.assertFalse(self.press())
        ManualTimer.created[-1].fire()
        self.assertEqual(self.rec.events, ["short_up"])

    def test_press_after_window_is_a_new_single_press(self):
        self.press()
        ManualTimer.created[0].fire()
        self.assertFalse(self.press())
        ManualTimer.created[1].fire()
        self.assertEqual(self.rec.events, ["short_up", "short_up"])

    def test_hold_is_unaffected_and_does_not_arm_double_press(self):
        self.press(held=True)
        self.assertEqual(self.rec.events, ["hold_stop"])
        self.assertFalse(self.press(bound=False))
        self.assertEqual(self.rec.events, ["hold_stop", "short_up"])

    def test_cancel_drops_pending_short_up(self):
        self.press()
        self.detector.cancel()
        self.assertTrue(ManualTimer.created[0].cancelled)
        self.assertFalse(self.press(bound=False))
        self.assertEqual(self.rec.events, ["short_up"])

    def test_cancel_between_down_and_up_of_double_press(self):
        self.press()
        self.assertTrue(self.detector.on_down())
        self.detector.cancel()
        # The release no longer belongs to a double press
        self.detector.on_release(held=False, double_press_bound=False,
                                 emit_short_up=self.rec.short_up, emit_hold_stop=self.rec.hold_stop)
        self.assertEqual(self.rec.events, ["short_up"])

    def test_timer_firing_after_cancel_race_does_nothing(self):
        self.press()
        timer = ManualTimer.created[0]
        self.assertTrue(self.detector.on_down())
        # Timer thread already past cancel() when the second press arrived
        timer.function()
        self.assertEqual(self.rec.events, [])


class TestDoublePressRealTimer(unittest.TestCase):
    def test_short_up_arrives_after_window_on_timer_thread(self):
        done = threading.Event()
        fired_at = []
        detector = DoublePressDetector(get_window=lambda: 0.05)
        start = time.monotonic()
        detector.on_down()
        detector.on_release(held=False, double_press_bound=True,
                            emit_short_up=lambda: (fired_at.append(time.monotonic()), done.set()),
                            emit_hold_stop=lambda: None)
        self.assertTrue(done.wait(2))
        self.assertGreaterEqual(fired_at[0] - start, 0.05)


class TestDoublePressEvents(unittest.TestCase):
    def test_events_exist_for_keys_dials_and_touch_keys(self):
        self.assertEqual(str(Input.Key.Events.DOUBLE_PRESS), "Key Double Press")
        self.assertEqual(str(Input.Dial.Events.DOUBLE_PRESS), "Dial Double Press")
        self.assertIs(Input.TouchKey.Events.DOUBLE_PRESS, Input.Key.Events.DOUBLE_PRESS)

    def test_event_names_round_trip(self):
        # Page json stores events by string name, so names must be unique
        names = [event.string_name for event in Input.AllEvents()]
        self.assertEqual(len(names), len(set(names)))
        for event in (Input.Key.Events.DOUBLE_PRESS, Input.Dial.Events.DOUBLE_PRESS):
            self.assertIs(Input.EventFromStringName(event.string_name), event)


if __name__ == "__main__":
    unittest.main()
