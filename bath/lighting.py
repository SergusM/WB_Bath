"""Освещение: бра, RGB-подсветка и мастер-клавиша."""

from __future__ import annotations

from typing import Dict

from . import io_config as cfg
from .io_config import Room
from .gateway import BaseGateway

RGB_RELAYS = {Room.SPA: cfg.RGB_SPA, Room.STEAM: cfg.RGB_STEAM}
RGB_WHITE = 1


class LightController:
    """Сцена (бра + RGB) и маска мастер-клавиши.

    Маска гасит выходы, но сцену помнит: повторное нажатие мастера её
    возвращает. Любая команда света снимает маску.
    """

    def __init__(self, gw: BaseGateway):
        self.gw = gw
        self.sconce = 0                                   # индекс SCONCE_MODES
        self.rgb: Dict[Room, int] = {Room.SPA: 0, Room.STEAM: 0}   # индекс RGB_MODES
        self.masked = False

    @property
    def scene_on(self) -> bool:
        return self.sconce != 0 or any(self.rgb.values())

    # --- бра -------------------------------------------------------------

    def sconce_next(self) -> None:
        self.masked = False
        self.sconce = (self.sconce + 1) % len(cfg.SCONCE_MODES)

    def set_sconce(self, spa: bool, steam: bool) -> None:
        self.masked = False
        self.sconce = cfg.SCONCE_MODES.index((int(bool(spa)), int(bool(steam))))

    def sconce_steam_toggle(self) -> None:
        spa, steam = cfg.SCONCE_MODES[self.sconce]
        self.set_sconce(spa, not steam)

    # --- RGB -------------------------------------------------------------

    def rgb_next(self, room: Room) -> None:
        """Следующий цвет по кругу 1..7 (выключение — отдельной командой)."""
        self.masked = False
        self.rgb[room] = self.rgb[room] % (len(cfg.RGB_MODES) - 1) + 1

    def set_rgb(self, room: Room, mode: int) -> None:
        mode = int(mode)
        if not 0 <= mode < len(cfg.RGB_MODES):
            raise ValueError(f"режим RGB должен быть от 0 до {len(cfg.RGB_MODES) - 1}")
        self.masked = False
        self.rgb[room] = mode

    def rgb_off(self, room: Room) -> None:
        self.set_rgb(room, 0)

    # --- общее -----------------------------------------------------------

    def master(self) -> None:
        """Короткое нажатие мастер-клавиши."""
        if self.masked:
            self.masked = False
        elif self.scene_on:
            self.masked = True
        else:
            self.sconce = cfg.SCONCE_MODES.index((1, 1))
            self.rgb = {room: RGB_WHITE for room in self.rgb}

    def all_off(self) -> None:
        self.sconce = 0
        self.rgb = {room: 0 for room in self.rgb}
        self.masked = False

    def apply(self) -> None:
        spa, steam = (0, 0) if self.masked else cfg.SCONCE_MODES[self.sconce]
        self.gw.set_relay(cfg.R_SCONCE_SPA, spa)
        self.gw.set_relay(cfg.R_SCONCE_STEAM, steam)
        for room, relays in RGB_RELAYS.items():
            colors = cfg.RGB_MODES[0 if self.masked else self.rgb[room]]
            for relay, on in zip(relays, colors):
                self.gw.set_relay(relay, on)
