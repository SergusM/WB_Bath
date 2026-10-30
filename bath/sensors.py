"""Показания датчиков температуры с учётом ошибок и устаревания."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from . import io_config as cfg
from .io_config import TempSensor
from .gateway import path

OK = "ok"
NO_DATA = "no_data"   # ещё не было показаний (первые SENSOR_STALE_S после старта)
STALE = "stale"       # показаний нет дольше SENSOR_STALE_S
ERROR = "error"       # wb-mqtt-serial выставил meta/error


@dataclass
class Reading:
    temp: Optional[float]   # None, если показанию нельзя верить
    status: str
    error: str = ""


@dataclass
class _Slot:
    value: Optional[float] = None
    updated: Optional[float] = None
    error: str = ""


class SensorStore:
    def __init__(self, sensors: Iterable[TempSensor], started: float,
                 stale_s: float = cfg.SENSOR_STALE_S):
        self._sensors = {path(s): s for s in sensors}
        self._slots: Dict[str, _Slot] = {k: _Slot() for k in self._sensors}
        self._started = started
        self._stale_s = stale_s

    def update(self, key: str, value, now: float) -> None:
        slot = self._slots.get(key)
        if slot is None:
            return
        try:
            slot.value = float(value) + self._sensors[key].correction
        except (TypeError, ValueError):
            slot.value = None
        slot.updated = now

    def set_error(self, key: str, error, now: float) -> None:
        slot = self._slots.get(key)
        if slot is not None:
            slot.error = str(error or "").strip()

    def get(self, sensor: TempSensor, now: float) -> Reading:
        slot = self._slots[path(sensor)]
        if slot.error:
            return Reading(None, ERROR, slot.error)
        if slot.updated is None:
            status = NO_DATA if now - self._started < self._stale_s else STALE
            return Reading(None, status)
        if now - slot.updated > self._stale_s:
            return Reading(None, STALE)
        if slot.value is None:
            return Reading(None, ERROR, "value")
        return Reading(slot.value, OK)
