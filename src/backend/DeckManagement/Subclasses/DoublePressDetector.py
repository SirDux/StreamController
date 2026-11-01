"""
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This programm comes with ABSOLUTELY NO WARRANTY!

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
import threading
from typing import Callable


class DoublePressDetector:
    """
    Recognises double presses on one input (key, dial or touch key).

    It only changes anything while the input has an action bound to its double press
    event. Then the short-up of a first press is held back for the double press window:
    if no second press arrives in that window the short-up is sent late, otherwise the
    second press becomes a double press and its release sends neither short-up nor hold
    events. Down and up events are never delayed or dropped.

    The deck read thread calls on_down/on_release, the window timer runs on its own
    thread, so all bookkeeping happens under a lock.
    """

    def __init__(self, get_window: Callable[[], float], timer_factory: Callable = threading.Timer):
        self._get_window = get_window
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._pending_timer = None
        # Set when the current press is the second half of a double press
        self._consume_release: bool = False

    def on_down(self) -> bool:
        """
        Call on every press. Returns True if this press completes a double press - the
        caller should then send the double press event and not start the hold timer.
        """
        with self._lock:
            if self._pending_timer is None:
                return False
            self._pending_timer.cancel()
            self._pending_timer = None
            self._consume_release = True
            return True

    def on_release(self, held: bool, double_press_bound: bool,
                   emit_short_up: Callable[[], None], emit_hold_stop: Callable[[], None]) -> None:
        """Call on every release that follows a press, instead of sending short-up/hold-stop directly."""
        with self._lock:
            if self._consume_release:
                self._consume_release = False
                return

            if held:
                emit = emit_hold_stop
            elif double_press_bound:
                timer = None

                def fire():
                    with self._lock:
                        # A second press may have cancelled us right as the timer fired
                        if self._pending_timer is not timer:
                            return
                        self._pending_timer = None
                    emit_short_up()

                timer = self._timer_factory(self._get_window(), fire)
                timer.daemon = True
                self._pending_timer = timer
                timer.start()
                return
            else:
                emit = emit_short_up

        emit()

    def cancel(self) -> None:
        """Forget any half-finished double press, e.g. because the page changed."""
        with self._lock:
            if self._pending_timer is not None:
                self._pending_timer.cancel()
                self._pending_timer = None
            self._consume_release = False
