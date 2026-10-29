"""Обливное устройство (с расписанием) и запарник."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

import io_config as cfg

from .gateway import BaseGateway
from .storage import WEEKDAYS, SettingsStore, WaterfallSchedule


def parse_time(text: str) -> Tuple[int, int]:
    hours, minutes = str(text).split(":")
    h, m = int(hours), int(minutes)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"неверное время {text!r}")
    return h, m


class Waterfall:
    """Пролив: клапан открыт ровно duration секунд.

    Физическая кнопка, интерфейс и расписание вызывают один pour().
    Повторный pour во время пролива продлевает его.
    """

    def __init__(self, gw: BaseGateway, store: SettingsStore):
        self.gw = gw
        self.store = store
        self._until: Optional[float] = None
        self._last_fired: Optional[Tuple[str, int, int]] = None

    @property
    def duration(self) -> float:
        return self.store.settings.waterfall_duration

    @property
    def schedule(self) -> WaterfallSchedule:
        return self.store.settings.waterfall_schedule

    def pour(self, now: float, duration: Optional[float] = None) -> None:
        d = self.duration if duration is None else self._check_duration(duration)
        self._until = now + d

    def stop(self) -> None:
        self._until = None

    def left(self, now: float) -> Optional[float]:
        if self._until is None:
            return None
        return max(0.0, self._until - now)

    def set_duration(self, duration: float, now: float) -> None:
        self.store.settings.waterfall_duration = self._check_duration(duration)
        self.store.changed(now)

    def set_schedule(self, now: float, enabled: Optional[bool] = None,
                     times: Optional[List[str]] = None,
                     days: Optional[List[str]] = None) -> None:
        sch = self.schedule
        if times is not None:
            parsed = sorted({parse_time(t) for t in times})
            times = [f"{h:02d}:{m:02d}" for h, m in parsed]
        if days is not None:
            bad = [d for d in days if d not in WEEKDAYS]
            if bad:
                raise ValueError(f"неизвестные дни {bad}, допустимо {list(WEEKDAYS)}")
            days = [d for d in WEEKDAYS if d in days]
        if enabled is not None:
            sch.enabled = bool(enabled)
        if times is not None:
            sch.times = times
        if days is not None:
            sch.days = days
        self.store.changed(now)

    def tick(self, now: float, wall: datetime) -> bool:
        """Возвращает True, если пролив запущен расписанием."""
        left = self.left(now)
        if left is not None and left <= 0:
            self.stop()
        sch = self.schedule
        if not sch.enabled or WEEKDAYS[wall.weekday()] not in sch.days:
            return False
        hm = f"{wall.hour:02d}:{wall.minute:02d}"
        fired = (wall.date().isoformat(), wall.hour, wall.minute)
        if hm in sch.times and fired != self._last_fired:
            self._last_fired = fired
            self.pour(now)
            return True
        return False

    def apply(self) -> None:
        self.gw.set_relay(cfg.R_WATERFALL, self._until is not None)

    @staticmethod
    def _check_duration(duration: float) -> float:
        d = float(duration)
        if not 1 <= d <= cfg.WATERFALL_MAX_S:
            raise ValueError(f"длительность должна быть от 1 до {cfg.WATERFALL_MAX_S} с")
        return d


class Zaparnik:
    """Режим запарника. Нагрев по датчику ведёт HeatingController."""

    def __init__(self, gw: BaseGateway):
        self.gw = gw
        self.on = False

    def set(self, on: Optional[bool]) -> None:
        """on=None — переключить."""
        self.on = (not self.on) if on is None else bool(on)

    def apply(self) -> None:
        for relay in cfg.BTN_ZAPARNIK.indicators:
            self.gw.set_relay(relay, self.on)
