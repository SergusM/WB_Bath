"""Вентиляция (общая на СПА и парную) и лицевой фен."""

from __future__ import annotations

from typing import Optional

import io_config as cfg
from io_config import VentMode

from .gateway import BaseGateway


class VentController:
    """Режимы X0–X3 взаимоисключающие, у «Парового душа» ступени 1–4.

    Кнопки обеих комнат и команды интерфейса управляют одним состоянием,
    индикаторы СПА и парной выставляются одновременно.
    """

    def __init__(self, gw: BaseGateway):
        self.gw = gw
        self.mode = VentMode.STEAMING
        self.stage = 0
        self._airing_since: Optional[float] = None

    def press(self, mode: VentMode, now: float) -> None:
        """Нажатие кнопки режима (физической или в интерфейсе)."""
        if mode is VentMode.STEAM_SHOWER:
            stage = self.stage + 1 if self.mode is VentMode.STEAM_SHOWER else 1
            if stage > cfg.STEAM_SHOWER_STAGES:
                self.set(VentMode.STEAMING, now=now)
            else:
                self.set(VentMode.STEAM_SHOWER, stage, now)
        else:
            self.set(mode, now=now)

    def set(self, mode: VentMode, stage: Optional[int] = None,
            now: float = 0.0) -> None:
        if mode is VentMode.STEAM_SHOWER:
            stage = 1 if stage is None else int(stage)
            if not 1 <= stage <= cfg.STEAM_SHOWER_STAGES:
                raise ValueError(f"ступень должна быть от 1 до {cfg.STEAM_SHOWER_STAGES}")
        else:
            stage = 0
        self.mode, self.stage = mode, stage
        # Таймер «Проветривания» перезапускается каждым нажатием
        self._airing_since = now if mode is VentMode.AIRING else None

    def airing_left(self, now: float) -> Optional[float]:
        if self._airing_since is None:
            return None
        return max(0.0, cfg.VENT_AUTO_RETURN_S - (now - self._airing_since))

    def tick(self, now: float) -> None:
        left = self.airing_left(now)
        if left is not None and left <= 0:
            self.set(VentMode.STEAMING, now=now)

    def apply(self) -> None:
        active = set(cfg.VENT_PATTERNS[(self.mode, self.stage)])
        for i, relay in enumerate(cfg.VENT):
            self.gw.set_relay(relay, i in active)
        for buttons in cfg.VENT_BUTTONS.values():
            for mode, button in buttons.items():
                for relay in button.indicators:
                    self.gw.set_relay(relay, mode is self.mode)


class FaceFan:
    """Лицевой фен, автоотключение через FACE_FAN_AUTO_OFF_S."""

    def __init__(self, gw: BaseGateway):
        self.gw = gw
        self.on = False
        self._since: Optional[float] = None

    def set(self, on: Optional[bool], now: float) -> None:
        """on=None — переключить."""
        self.on = (not self.on) if on is None else bool(on)
        self._since = now if self.on else None

    def left(self, now: float) -> Optional[float]:
        if self._since is None:
            return None
        return max(0.0, cfg.FACE_FAN_AUTO_OFF_S - (now - self._since))

    def tick(self, now: float) -> None:
        left = self.left(now)
        if left is not None and left <= 0:
            self.set(False, now)

    def apply(self) -> None:
        for relay in cfg.BTN_FACE_FAN.indicators:
            self.gw.set_relay(relay, self.on)
