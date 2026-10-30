"""Нагрев: режимы комнат, уставки, гистерезис и защиты."""

from __future__ import annotations

import dataclasses
from typing import Callable, Dict, Optional, Union

from . import io_config as cfg
from .io_config import HeatZone, Preset, Room, RoomSetpoints, ZoneKind
from .alarms import AlarmLog
from .gateway import BaseGateway, path
from .sensors import ERROR, STALE, Reading, SensorStore
from .storage import SettingsStore

MANUAL = "manual"
Mode = Union[Preset, str]   # Preset или MANUAL


def hysteresis(setpoint: float, temp: Optional[float], prev: bool,
               h: float) -> bool:
    """Вкл ниже SP-h, выкл выше SP+h, между ними — без изменений."""
    if setpoint <= 0 or temp is None:
        return False
    if temp < setpoint - h:
        return True
    if temp > setpoint + h:
        return False
    return prev


class HeatingController:
    def __init__(self, gw: BaseGateway, sensors: SensorStore, alarms: AlarmLog,
                 store: SettingsStore, zaparnik_on: Callable[[], bool]):
        self.gw = gw
        self.sensors = sensors
        self.alarms = alarms
        self.store = store
        self.zaparnik_on = zaparnik_on
        self.mode: Dict[Room, Mode] = {Room.SPA: Preset.OFF, Room.STEAM: Preset.OFF}
        self.readings: Dict[HeatZone, Reading] = {}
        self._demand: Dict[HeatZone, bool] = {}

    # --- команды ---------------------------------------------------------

    def set_preset(self, room: Room, preset: Preset) -> None:
        self.mode[room] = preset

    def set_manual(self, room: Room) -> None:
        self.mode[room] = MANUAL

    def room_off(self, room: Room) -> None:
        self.mode[room] = Preset.OFF

    def all_off(self) -> None:
        for room in self.mode:
            self.mode[room] = Preset.OFF

    def set_manual_setpoint(self, room: Room, kind: ZoneKind, value: float,
                            now: float) -> None:
        """Ручная уставка по типу поверхности. В ручном режиме действует сразу."""
        if kind is ZoneKind.STOVE:
            if room is not Room.STEAM:
                raise ValueError("печка есть только в парной")
            limit = cfg.STOVE_MAX_SETPOINT
        else:
            limit = cfg.ZONE_MAX_SETPOINT
        value = float(value)
        if not 0 <= value <= limit:
            raise ValueError(f"уставка должна быть от 0 до {limit}")
        manual = self.store.settings.manual
        manual[room] = dataclasses.replace(manual[room], **{kind.name.lower(): value})
        self.store.changed(now)

    # --- расчёт ----------------------------------------------------------

    def room_setpoints(self, room: Room) -> RoomSetpoints:
        mode = self.mode[room]
        if mode == MANUAL:
            return self.store.settings.manual[room]
        return cfg.PRESET_SETPOINTS[mode]

    def setpoint(self, zone: HeatZone) -> float:
        if zone is cfg.ZONE_ZAPARNIK:
            return cfg.ZAPARNIK_SETPOINT if self.zaparnik_on() else 0.0
        return self.room_setpoints(zone.room).get(zone.kind)

    def update(self, now: float) -> None:
        want: Dict[HeatZone, bool] = {}
        for zone in cfg.ALL_ZONES:
            reading = self.sensors.get(zone.sensor, now)
            self.readings[zone] = reading
            self._check_sensor(zone, reading)

            over = reading.temp is not None and reading.temp > zone.max_temp
            self.alarms.set(
                f"overheat:{path(zone.relay)}", over,
                f"Перегрев «{zone.relay.name}»: {reading.temp:.0f} °C > {zone.max_temp:.0f} °C"
                if over else "")

            demand = hysteresis(self.setpoint(zone), reading.temp,
                                self._demand.get(zone, False), zone.hysteresis)
            self._demand[zone] = demand
            want[zone] = demand and not over

        # Потолки СПА греют только парой
        a, b = cfg.SPA_CEILING_PAIR
        if not (want[a] and want[b]):
            want[a] = want[b] = False

        # Испаритель и парогенератор выключаются вместе, если хоть один датчик
        # неисправен или показывает перегрев
        if any(self.readings[z].temp is None or self.readings[z].temp > z.max_temp
               for z in cfg.STEAM_GEN_GROUP):
            for z in cfg.STEAM_GEN_GROUP:
                want[z] = False

        for zone, on in want.items():
            self.gw.set_relay(zone.relay, on)

    def heating(self, zone: HeatZone) -> bool:
        return self.gw.target(zone.relay)

    def force_off(self) -> None:
        """Немедленно выключить все нагреватели (старт, останов, авария)."""
        self._demand.clear()
        for zone in cfg.ALL_ZONES:
            self.gw.set_relay(zone.relay, False)

    def _check_sensor(self, zone: HeatZone, reading: Reading) -> None:
        bad = reading.status in (ERROR, STALE)
        what = ("нет показаний" if reading.status == STALE
                else f"ошибка {reading.error}")
        self.alarms.set(f"sensor:{path(zone.sensor)}", bad,
                        f"Датчик «{zone.sensor.name}»: {what}")
