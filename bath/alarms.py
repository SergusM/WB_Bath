"""Журнал аварий: активные и последние сработавшие."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Deque, Dict, Optional

Emit = Callable[[dict], None]


@dataclass
class Alarm:
    key: str
    message: str
    since: str            # ISO-время возникновения
    cleared: str = ""     # ISO-время снятия, пусто — активна
    acked: bool = False


class AlarmLog:
    def __init__(self, emit: Optional[Emit] = None,
                 wallclock: Callable[[], datetime] = datetime.now,
                 history: int = 50):
        self._emit = emit or (lambda e: None)
        self._now = wallclock
        self.active: Dict[str, Alarm] = {}
        self.history: Deque[Alarm] = deque(maxlen=history)

    def raise_(self, key: str, message: str) -> None:
        if key in self.active:
            return
        alarm = Alarm(key, message, self._stamp())
        self.active[key] = alarm
        self.history.appendleft(alarm)
        self._emit({"type": "alarm", **asdict(alarm)})

    def clear(self, key: str) -> None:
        alarm = self.active.pop(key, None)
        if alarm is not None:
            alarm.cleared = self._stamp()
            self._emit({"type": "alarm_cleared", **asdict(alarm)})

    def set(self, key: str, active: bool, message: str = "") -> None:
        if active:
            self.raise_(key, message)
        else:
            self.clear(key)

    def ack_all(self) -> None:
        for alarm in self.history:
            alarm.acked = True

    def snapshot(self) -> dict:
        return {
            "active": [asdict(a) for a in self.active.values()],
            "history": [asdict(a) for a in self.history],
            "unacked": sum(1 for a in self.history if not a.acked),
        }

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")
