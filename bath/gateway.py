"""Связь с контроллером: команды реле и входящие события.

Все колбэки MQTT (они приходят из потока paho) только кладут Event в очередь
events. Логика читает очередь в одном потоке, поэтому локи не нужны.
"""

from __future__ import annotations

import logging
import queue
from collections import OrderedDict
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from . import io_config as cfg
from .io_config import Relay

log = logging.getLogger(__name__)


class Event(NamedTuple):
    kind: str      # input | sensor | sensor_error | relay_state | energy | cmd
    key: str       # "device/control" или MQTT-топик для cmd
    value: object


def path(control) -> str:
    return f"{control.device}/{control.control}"


class BaseGateway:
    """Кэш команд реле и очередь включения нагревателей.

    Включение нагревателя не пишется сразу, а встаёт в очередь: flush()
    отправляет не больше одной такой команды раз в HEATER_ON_DELAY_S, чтобы
    контакторы не включались пачкой. Выключение пишется сразу и снимает из
    очереди невыполненное включение этого реле.
    """

    def __init__(self, heater_relays: Iterable[Relay],
                 on_delay: float = cfg.HEATER_ON_DELAY_S):
        self.events: "queue.Queue[Event]" = queue.Queue()
        self._heaters = set(heater_relays)
        self._on_delay = on_delay
        self._target: Dict[Relay, bool] = {}
        self._actual: Dict[Relay, bool] = {}
        self._pending_on: "OrderedDict[Relay, None]" = OrderedDict()
        self._last_on_sent = float("-inf")
        self._last_resync = float("-inf")
        self._suspect: Set[Relay] = set()
        self._by_path = {path(r): r for r in cfg.ALL_RELAYS}

    # --- запись ----------------------------------------------------------

    def set_relay(self, relay: Relay, on: bool) -> None:
        on = bool(on)
        if self._target.get(relay) == on:
            return
        self._target[relay] = on
        if on and relay in self._heaters:
            self._pending_on[relay] = None
            return
        self._pending_on.pop(relay, None)
        self._write(relay, on)

    def has_pending(self) -> bool:
        return bool(self._pending_on)

    def flush(self, now: float) -> None:
        if not self._pending_on or now - self._last_on_sent < self._on_delay:
            return
        relay, _ = self._pending_on.popitem(last=False)
        self._last_on_sent = now
        self._write(relay, True)

    def resync(self, now: float) -> Optional[List[Relay]]:
        """Повторяет команду реле, если обратная связь с ней расходится.

        Возвращает None, если сверка ещё не нужна, иначе реле, которые
        расходятся вторую сверку подряд (то есть повтор команды не помог).
        """
        if now - self._last_resync < cfg.RELAY_RESYNC_S:
            return None
        self._last_resync = now
        mismatched = []
        for relay, on in self._target.items():
            actual = self._actual.get(relay)
            if actual is None or actual == on or relay in self._pending_on:
                continue
            mismatched.append(relay)
            log.warning("Реле %s: команда %d, факт %d, повторяю",
                        relay.name, on, actual)
            if on and relay in self._heaters:
                self._pending_on[relay] = None
            else:
                self._write(relay, on)
        stuck = [r for r in mismatched if r in self._suspect]
        self._suspect = set(mismatched)
        return stuck

    # --- чтение ----------------------------------------------------------

    def target(self, relay: Relay) -> bool:
        return self._target.get(relay, False)

    def actual(self, relay: Relay) -> Optional[bool]:
        return self._actual.get(relay)

    def on_relay_state(self, key: str, value) -> None:
        relay = self._by_path.get(key)
        if relay is not None:
            try:
                self._actual[relay] = bool(int(value))
            except (TypeError, ValueError):
                pass

    # --- для наследников -------------------------------------------------

    def _write(self, relay: Relay, on: bool) -> None:
        raise NotImplementedError

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class WbGateway(BaseGateway):
    """Работа с брокером Wiren Board через python2wb."""

    def __init__(self, host: str, port: int = 1883,
                 username: Optional[str] = None, password: Optional[str] = None):
        super().__init__(z.relay for z in cfg.ALL_ZONES)
        from python2wb.mqtt import WbMqtt  # импорт здесь, чтобы тесты шли без paho

        self.wb = WbMqtt(host, port, username=username, password=password,
                         driver_name="wb_bath")
        put = self.events.put

        def on_input(dev, ctrl, value):
            put(Event("input", f"{dev}/{ctrl}", value))

        def on_sensor(dev, ctrl, value):
            put(Event("sensor", f"{dev}/{ctrl}", value))

        def on_sensor_error(dev, ctrl, value):
            put(Event("sensor_error", f"{dev}/{ctrl}", value))

        def on_relay(dev, ctrl, value):
            put(Event("relay_state", f"{dev}/{ctrl}", value))

        def on_energy(dev, ctrl, value):
            put(Event("energy", f"{dev}/{ctrl}", value))

        def on_cmd(topic, value):
            put(Event("cmd", topic, value))

        sensors = [path(s) for s in cfg.ALL_TEMP_SENSORS]
        self.wb.subscribe([path(i) for i in cfg.ALL_INPUTS], on_input)
        self.wb.subscribe(sensors, on_sensor)
        self.wb.subscribe_errors(sensors, on_sensor_error)
        self.wb.subscribe([path(r) for r in cfg.ALL_RELAYS], on_relay)
        self.wb.subscribe([path(c) for c in cfg.ENERGY_METER], on_energy)
        self.wb.subscribe_raw(f"{cfg.APP_PREFIX}/cmd", on_cmd)
        self.wb.loop_start()

    def _write(self, relay: Relay, on: bool) -> None:
        log.debug("-> %s = %d", relay.name, on)
        self.wb.set(path(relay), int(on))

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.wb.publish_raw(topic, payload, retain=retain)

    def close(self) -> None:
        self.wb.clear()


class FakeGateway(BaseGateway):
    """Шлюз для тестов: пишет команды в список, обратная связь мгновенная."""

    def __init__(self, on_delay: float = cfg.HEATER_ON_DELAY_S,
                 feedback: bool = True):
        super().__init__((z.relay for z in cfg.ALL_ZONES), on_delay)
        self.feedback = feedback
        self.writes: List[Tuple[Relay, bool]] = []
        self.published: List[Tuple[str, str, bool]] = []

    def _write(self, relay: Relay, on: bool) -> None:
        self.writes.append((relay, on))
        if self.feedback:
            self._actual[relay] = on

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.published.append((topic, payload, retain))

    def inject(self, kind: str, key: str, value) -> None:
        self.events.put(Event(kind, key, value))
