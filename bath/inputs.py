"""Разбор нажатий физических кнопок (входы WB присылают 0/1)."""

from __future__ import annotations

from typing import Callable, Optional

Action = Callable[[float], None]


class ButtonTracker:
    """Одна кнопка.

    Без long_s действие on_short выполняется сразу по нажатию (фронт 0→1).
    С long_s: удержание дольше long_s вызывает on_long (из tick, не дожидаясь
    отпускания), короткое нажатие — on_short при отпускании.
    Первое значение после подключения (retained) нажатием не считается.
    """

    def __init__(self, on_short: Action, long_s: Optional[float] = None,
                 on_long: Optional[Action] = None):
        self.on_short = on_short
        self.long_s = long_s
        self.on_long = on_long
        self._state: Optional[bool] = None
        self._pressed_at: Optional[float] = None
        self._long_fired = False

    def update(self, value, now: float) -> None:
        try:
            pressed = bool(int(value))
        except (TypeError, ValueError):
            return
        prev, self._state = self._state, pressed
        if prev is None or prev == pressed:
            return
        if pressed:
            self._pressed_at = now
            self._long_fired = False
            if self.long_s is None:
                self.on_short(now)
        else:
            was_pressed = self._pressed_at is not None
            self._pressed_at = None
            if self.long_s is not None and was_pressed and not self._long_fired:
                self.on_short(now)

    def tick(self, now: float) -> None:
        if (self.long_s is not None and self._pressed_at is not None
                and not self._long_fired and now - self._pressed_at >= self.long_s):
            self._long_fired = True
            if self.on_long is not None:
                self.on_long(now)
