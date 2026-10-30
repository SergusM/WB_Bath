"""Пользовательские настройки в JSON.

Сохраняются только настройки (ручные уставки, обливное). Выбранные режимы
нагрева, вентиляции и света не сохраняются: после старта всё выключено.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Dict, List, Optional

from . import io_config as cfg
from .io_config import Room, RoomSetpoints

log = logging.getLogger(__name__)

ROOM_KEYS = {Room.SPA: "spa", Room.STEAM: "steam"}
ROOMS_BY_KEY = {v: k for k, v in ROOM_KEYS.items()}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SAVE_DELAY_S = 2.0


def _zero_setpoints() -> RoomSetpoints:
    return cfg.PRESET_SETPOINTS[cfg.Preset.OFF]


@dataclass
class WaterfallSchedule:
    enabled: bool = False
    times: List[str] = field(default_factory=list)   # "HH:MM"
    days: List[str] = field(default_factory=lambda: list(WEEKDAYS))


@dataclass
class Settings:
    manual: Dict[Room, RoomSetpoints] = field(default_factory=lambda: {
        Room.SPA: _zero_setpoints(), Room.STEAM: _zero_setpoints()})
    waterfall_duration: float = cfg.WATERFALL_DEFAULT_S
    waterfall_schedule: WaterfallSchedule = field(default_factory=WaterfallSchedule)

    def to_json(self) -> dict:
        return {
            "manual": {ROOM_KEYS[r]: asdict(sp) for r, sp in self.manual.items()},
            "waterfall": {
                "duration": self.waterfall_duration,
                "schedule": asdict(self.waterfall_schedule),
            },
        }

    @classmethod
    def from_json(cls, data: dict) -> "Settings":
        s = cls()
        names = {f.name for f in fields(RoomSetpoints)}
        for key, sp in (data.get("manual") or {}).items():
            room = ROOMS_BY_KEY.get(key)
            if room is not None:
                values = asdict(s.manual[room])
                values.update({k: float(v) for k, v in sp.items() if k in names})
                s.manual[room] = RoomSetpoints(**values)
        wf = data.get("waterfall") or {}
        if "duration" in wf:
            s.waterfall_duration = float(wf["duration"])
        sch = wf.get("schedule") or {}
        s.waterfall_schedule = WaterfallSchedule(
            enabled=bool(sch.get("enabled", False)),
            times=[str(t) for t in sch.get("times", [])],
            days=[d for d in sch.get("days", WEEKDAYS) if d in WEEKDAYS],
        )
        return s


class SettingsStore:
    def __init__(self, filename: str):
        self.filename = filename
        self.settings = self._load()
        self._save_at: Optional[float] = None

    def changed(self, now: float) -> None:
        """Отложенное сохранение: пачка изменений пишется одним файлом."""
        self._save_at = now + SAVE_DELAY_S

    def tick(self, now: float) -> None:
        if self._save_at is not None and now >= self._save_at:
            self.save()

    def save(self) -> None:
        self._save_at = None
        tmp = self.filename + ".tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.filename)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.settings.to_json(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.filename)
        except OSError:
            log.exception("Не удалось сохранить настройки в %s", self.filename)

    def flush(self) -> None:
        if self._save_at is not None:
            self.save()

    def _load(self) -> Settings:
        if not os.path.exists(self.filename):
            log.info("Файла настроек %s нет, беру значения по умолчанию", self.filename)
            return Settings()
        try:
            with open(self.filename, encoding="utf-8") as f:
                return Settings.from_json(json.load(f))
        except (OSError, ValueError, TypeError, AttributeError):
            log.exception("Файл настроек %s испорчен, беру значения по умолчанию",
                          self.filename)
            return Settings()
