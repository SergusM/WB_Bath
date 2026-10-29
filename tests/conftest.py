import json
from datetime import datetime

import pytest

import io_config as cfg
from bath.controller import BathController
from bath.gateway import Event, FakeGateway, path
from bath.storage import SettingsStore


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class Wall:
    def __init__(self, dt: datetime):
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


class Rig:
    """Контроллер на FakeGateway с управляемым временем."""

    def __init__(self, tmp_path):
        self.clock = Clock()
        self.wall = Wall(datetime(2026, 10, 26, 12, 0))   # понедельник
        self.gw = FakeGateway()
        self.store = SettingsStore(str(tmp_path / "settings.json"))
        self.ctl = BathController(self.gw, self.store, self.clock, self.wall)
        self.ctl.start()
        for inp in cfg.ALL_INPUTS:          # первое (retained) значение входов
            self.event("input", path(inp), 0)

    @property
    def now(self) -> float:
        return self.clock.t

    def advance(self, dt: float, tick: bool = True) -> None:
        self.clock.t += dt
        if tick:
            self.ctl.tick(self.now)

    def event(self, kind: str, key: str, value) -> None:
        self.ctl.handle(Event(kind, key, value), self.now)

    def temps(self, default: float = 20.0):
        """Все датчики зон = default (с учётом поправки)."""
        for zone in cfg.ALL_ZONES:
            self.temp(zone, default)

    def temp(self, zone, value: float) -> None:
        self.event("sensor", path(zone.sensor), value - zone.sensor.correction)

    def cmd(self, **data) -> dict:
        """Команда так, как она приходит из /app/cmd."""
        self.event("cmd", "/app/cmd", json.dumps(data))
        topic, payload, _ = [p for p in self.gw.published if p[0] == "/app/ack"][-1]
        return json.loads(payload)

    def press(self, button, hold: float = 0.05) -> None:
        key = path(button.input)
        self.event("input", key, 1)
        self.advance(hold)
        self.event("input", key, 0)

    def flush_all(self, step: float = 0.05, limit: int = 1000) -> None:
        for _ in range(limit):
            if not self.gw.has_pending():
                return
            self.clock.t += step
            self.gw.flush(self.now)
        raise AssertionError("очередь включения не опустела")

    def on(self, relay) -> bool:
        return self.gw.target(relay)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)
