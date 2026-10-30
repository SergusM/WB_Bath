"""Сборка подсистем, разбор событий и главный цикл."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

from . import io_config as cfg
from .io_config import Room
from .alarms import AlarmLog
from .api import (TOPIC_EVENT, TOPIC_INFO, TOPIC_ONLINE, CommandApi,
                  StatePublisher, build_info)
from .extras import Waterfall, Zaparnik
from .gateway import BaseGateway, Event, path
from .heating import HeatingController
from .inputs import ButtonTracker
from .lighting import LightController
from .sensors import SensorStore
from .storage import SettingsStore
from .ventilation import FaceFan, VentController

log = logging.getLogger(__name__)

TICK_S = 1.0


class BathController:
    def __init__(self, gw: BaseGateway, store: SettingsStore,
                 clock: Callable[[], float] = time.monotonic,
                 wallclock: Callable[[], datetime] = datetime.now):
        self.gw = gw
        self.store = store
        self.clock = clock
        self.wallclock = wallclock
        now = clock()

        self.alarms = AlarmLog(self.emit, wallclock)
        self.sensors = SensorStore(cfg.ALL_TEMP_SENSORS, now)
        self.zaparnik = Zaparnik(gw)
        self.heating = HeatingController(gw, self.sensors, self.alarms, store,
                                         lambda: self.zaparnik.on)
        self.vent = VentController(gw)
        self.face_fan = FaceFan(gw)
        self.light = LightController(gw)
        self.waterfall = Waterfall(gw, store)
        self.energy: Dict[str, object] = {}

        self.api = CommandApi(self)
        self.publisher = StatePublisher(self)
        self.buttons = self._make_buttons()
        self._next_tick = now

    # --- кнопки ----------------------------------------------------------

    def _make_buttons(self) -> Dict[str, ButtonTracker]:
        b: Dict[str, ButtonTracker] = {}
        for buttons in cfg.VENT_BUTTONS.values():
            for mode, button in buttons.items():
                b[path(button.input)] = ButtonTracker(
                    lambda now, m=mode: self.vent.press(m, now))

        def rgb(room: Room) -> ButtonTracker:
            return ButtonTracker(lambda now: self.light.rgb_next(room),
                                 cfg.LONG_PRESS_RGB_S,
                                 lambda now: self.light.rgb_off(room))

        b[path(cfg.BTN_LIGHT_STEAM.input)] = ButtonTracker(
            lambda now: self.light.light_steam_toggle())
        b[path(cfg.BTN_LIGHT_SPA.input)] = ButtonTracker(lambda now: self.light.light_next())
        b[path(cfg.BTN_RGB_STEAM.input)] = rgb(Room.STEAM)
        b[path(cfg.BTN_RGB_SPA.input)] = rgb(Room.SPA)
        b[path(cfg.BTN_MASTER.input)] = ButtonTracker(
            lambda now: self.light.master(), cfg.LONG_PRESS_MASTER_S,
            lambda now: self.offoff())
        b[path(cfg.BTN_ZAPARNIK.input)] = ButtonTracker(lambda now: self.zaparnik.set(None))
        b[path(cfg.BTN_FACE_FAN.input)] = ButtonTracker(
            lambda now: self.face_fan.set(None, now))
        b[path(cfg.BTN_WATERFALL.input)] = ButtonTracker(lambda now: self.waterfall.pour(now))
        return b

    # --- общие действия --------------------------------------------------

    def offoff(self) -> None:
        """«Выключить всё»: нагрев, свет, запарник, фен, обливное.

        Вентиляцию не трогаем, как и в старом потоке.
        """
        self.heating.all_off()
        self.light.all_off()
        self.zaparnik.set(False)
        self.face_fan.set(False, 0.0)
        self.waterfall.stop()

    def emit(self, event: dict) -> None:
        self.gw.publish(TOPIC_EVENT, json.dumps(event, ensure_ascii=False))

    def apply(self, now: float) -> None:
        self.heating.update(now)
        self.vent.apply()
        self.face_fan.apply()
        self.light.apply()
        self.waterfall.apply()
        self.zaparnik.apply()

    # --- жизненный цикл --------------------------------------------------

    def start(self) -> None:
        """Всё выключено, кроме R_ALWAYS_ON. Режимы после перезапуска не восстанавливаются."""
        now = self.clock()
        self.heating.force_off()
        self.apply(now)
        self.gw.set_relay(cfg.R_ALWAYS_ON, True)
        self.gw.publish(TOPIC_INFO, json.dumps(build_info(self.api.handlers),
                                               ensure_ascii=False), retain=True)
        self.gw.publish(TOPIC_ONLINE, "1", retain=True)
        log.info("Контроллер запущен")

    def shutdown(self) -> None:
        """Нагреватели и обливное выключаются сразу (выключение идёт мимо очереди)."""
        self.heating.force_off()
        self.waterfall.stop()
        self.waterfall.apply()
        self.store.flush()
        self.gw.publish(TOPIC_ONLINE, "0", retain=True)
        log.info("Контроллер остановлен, нагреватели выключены")

    def handle(self, ev: Event, now: float) -> None:
        if ev.kind == "sensor":
            self.sensors.update(ev.key, ev.value, now)
        elif ev.kind == "sensor_error":
            self.sensors.set_error(ev.key, ev.value, now)
        elif ev.kind == "relay_state":
            self.gw.on_relay_state(ev.key, ev.value)
        elif ev.kind == "energy":
            self.energy[ev.key.split("/", 1)[1]] = ev.value
        elif ev.kind == "input":
            tracker = self.buttons.get(ev.key)
            if tracker is not None:
                tracker.update(ev.value, now)
                self.apply(now)
        elif ev.kind == "cmd":
            self.api.handle(ev.value if isinstance(ev.value, str) else str(ev.value), now)
            self.apply(now)
        self.publisher.mark_dirty()

    def tick(self, now: float) -> None:
        for tracker in self.buttons.values():
            tracker.tick(now)
        self.vent.tick(now)
        self.face_fan.tick(now)
        if self.waterfall.tick(now, self.wallclock()):
            self.emit({"type": "waterfall_schedule"})
        self.apply(now)

        stuck = self.gw.resync(now)
        if stuck is not None:
            stuck_set = set(stuck)
            for relay in cfg.ALL_RELAYS:
                self.alarms.set(f"relay:{path(relay)}", relay in stuck_set,
                                f"Реле «{relay.name}» не выполняет команду")
        self.store.tick(now)
        self.publisher.mark_dirty()

    def step(self, timeout: Optional[float] = None) -> None:
        if timeout is None:
            timeout = 0.02 if self.gw.has_pending() else 0.2
        try:
            ev: Optional[Event] = self.gw.events.get(timeout=timeout)
        except queue.Empty:
            ev = None
        now = self.clock()
        if ev is not None:
            self.handle(ev, now)
        if now >= self._next_tick:
            self.tick(now)
            self._next_tick = now + TICK_S
        self.gw.flush(now)
        self.publisher.maybe_publish(now)

    def run(self, stop: threading.Event) -> None:
        self.start()
        while not stop.is_set():
            try:
                self.step()
            except Exception:
                # Логика не должна падать из-за одного плохого события,
                # но нагрев на время сбоя выключаем.
                log.exception("Ошибка в главном цикле, нагреватели выключены")
                self.heating.force_off()
