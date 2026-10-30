"""MQTT API для интерфейса.

<APP_PREFIX>/cmd    <- {"cmd": "...", ...аргументы, "id": "необязательно"}
<APP_PREFIX>/ack    -> {"id", "cmd", "ok", "error"?}
<APP_PREFIX>/state  -> полное состояние (retained)
<APP_PREFIX>/info   -> справочник: режимы, типы зон, пределы (retained)
<APP_PREFIX>/event  -> события: аварии, пролив по расписанию, ошибки команд
<APP_PREFIX>/online -> "1" пока сервис работает (retained)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Callable, Dict, Optional

from . import io_config as cfg
from .io_config import Preset, Room, VentMode, ZoneKind
from .heating import MANUAL
from .storage import ROOM_KEYS, ROOMS_BY_KEY, WEEKDAYS

if TYPE_CHECKING:
    from .controller import BathController

log = logging.getLogger(__name__)

TOPIC_CMD = f"{cfg.APP_PREFIX}/cmd"
TOPIC_ACK = f"{cfg.APP_PREFIX}/ack"
TOPIC_STATE = f"{cfg.APP_PREFIX}/state"
TOPIC_INFO = f"{cfg.APP_PREFIX}/info"
TOPIC_EVENT = f"{cfg.APP_PREFIX}/event"
TOPIC_ONLINE = f"{cfg.APP_PREFIX}/online"


class CommandError(ValueError):
    pass


# --- разбор аргументов -------------------------------------------------------

def _arg(d: dict, name: str):
    if name not in d:
        raise CommandError(f"нет аргумента {name!r}")
    return d[name]


def _room(d: dict) -> Room:
    key = _arg(d, "room")
    if key not in ROOMS_BY_KEY:
        raise CommandError(f"room: ожидается {list(ROOMS_BY_KEY)}")
    return ROOMS_BY_KEY[key]


def _preset(d: dict) -> Preset:
    try:
        return Preset(_arg(d, "preset"))
    except ValueError:
        raise CommandError(f"preset: ожидается {[p.value for p in Preset]}")


def _kind(d: dict) -> ZoneKind:
    try:
        return ZoneKind[str(_arg(d, "kind")).upper()]
    except KeyError:
        raise CommandError(f"kind: ожидается {[k.name for k in ZoneKind]}")


def _vent_mode(d: dict) -> VentMode:
    value = _arg(d, "mode")
    try:
        return VentMode(value) if isinstance(value, int) else VentMode[str(value).upper()]
    except (KeyError, ValueError):
        raise CommandError(f"mode: ожидается {[m.name for m in VentMode]}")


def _opt_bool(d: dict, name: str) -> Optional[bool]:
    value = d.get(name)
    return None if value is None else bool(value)


def mode_key(mode) -> str:
    return MANUAL if mode == MANUAL else mode.value


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 1)


def _seconds(value: Optional[float]) -> Optional[int]:
    return None if value is None else int(round(value))


# --- команды -----------------------------------------------------------------

class CommandApi:
    def __init__(self, ctl: "BathController"):
        self.ctl = ctl
        c = ctl
        self.handlers: Dict[str, Callable[[dict, float], None]] = {
            # нагрев
            "set_preset": lambda d, now: c.heating.set_preset(_room(d), _preset(d)),
            "set_manual": lambda d, now: c.heating.set_manual(_room(d)),
            "set_manual_setpoint": lambda d, now: c.heating.set_manual_setpoint(
                _room(d), _kind(d), _arg(d, "value"), now),
            "room_off": lambda d, now: c.heating.room_off(_room(d)),
            # вентиляция и фен
            "vent_press": lambda d, now: c.vent.press(_vent_mode(d), now),
            "vent_set": lambda d, now: c.vent.set(_vent_mode(d), d.get("stage"), now),
            "face_fan": lambda d, now: c.face_fan.set(_opt_bool(d, "on"), now),
            # свет
            "sconce_next": lambda d, now: c.light.sconce_next(),
            "set_sconce": lambda d, now: c.light.set_sconce(_arg(d, "spa"), _arg(d, "steam")),
            "rgb_next": lambda d, now: c.light.rgb_next(_room(d)),
            "set_rgb": lambda d, now: c.light.set_rgb(_room(d), _arg(d, "mode")),
            "rgb_off": lambda d, now: c.light.rgb_off(_room(d)),
            "master": lambda d, now: c.light.master(),
            "light_off": lambda d, now: c.light.all_off(),
            # обливное
            "waterfall_pour": lambda d, now: c.waterfall.pour(now, d.get("duration")),
            "waterfall_stop": lambda d, now: c.waterfall.stop(),
            "waterfall_set_duration": lambda d, now: c.waterfall.set_duration(
                _arg(d, "duration"), now),
            "waterfall_set_schedule": lambda d, now: c.waterfall.set_schedule(
                now, d.get("enabled"), d.get("times"), d.get("days")),
            # прочее
            "zaparnik": lambda d, now: c.zaparnik.set(_opt_bool(d, "on")),
            "offoff": lambda d, now: c.offoff(),
            "alarms_ack": lambda d, now: c.alarms.ack_all(),
            "get_state": lambda d, now: c.publisher.request(),
        }

    def handle(self, raw, now: float) -> dict:
        data: dict = {}
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            if not isinstance(data, dict):
                raise CommandError("ожидается JSON-объект")
            name = data.get("cmd")
            handler = self.handlers.get(name)
            if handler is None:
                raise CommandError(f"неизвестная команда {name!r}")
            handler(data, now)
            ack = {"ok": True}
        except (ValueError, TypeError) as e:   # CommandError и json.JSONDecodeError тоже
            log.warning("Команда %r отклонена: %s", raw, e)
            ack = {"ok": False, "error": str(e)}
        ack.update(id=data.get("id") if isinstance(data, dict) else None,
                   cmd=data.get("cmd") if isinstance(data, dict) else None)
        self.ctl.gw.publish(TOPIC_ACK, json.dumps(ack, ensure_ascii=False))
        return ack


# --- состояние ---------------------------------------------------------------

def build_state(ctl: "BathController", now: float) -> dict:
    settings = ctl.store.settings
    zones = []
    for z in cfg.ALL_ZONES:
        r = ctl.sensors.get(z.sensor, now)
        zones.append({
            "index": z.index,
            "name": z.name,
            "title": z.relay.name,
            "room": ROOM_KEYS.get(z.room),
            "kind": z.kind.name if z.kind else None,
            "temp": _round(r.temp),
            "status": r.status,
            "setpoint": ctl.heating.setpoint(z),
            "heating": ctl.gw.target(z.relay),
            "relay_actual": ctl.gw.actual(z.relay),
        })
    test = ctl.sensors.get(cfg.T_TEST_BLOCK, now)
    sconce_spa, sconce_steam = cfg.SCONCE_MODES[ctl.light.sconce]
    return {
        "heating": {
            ROOM_KEYS[room]: {
                "mode": mode_key(mode),
                "setpoints": asdict(ctl.heating.room_setpoints(room)),
                "manual": asdict(settings.manual[room]),
            } for room, mode in ctl.heating.mode.items()
        },
        "zones": zones,
        "test_block": {"temp": _round(test.temp), "status": test.status},
        "vent": {
            "mode": ctl.vent.mode.name,
            "stage": ctl.vent.stage,
            "airing_left_s": _seconds(ctl.vent.airing_left(now)),
        },
        "face_fan": {"on": ctl.face_fan.on, "left_s": _seconds(ctl.face_fan.left(now))},
        "light": {
            "sconce": {"spa": bool(sconce_spa), "steam": bool(sconce_steam)},
            "rgb": {ROOM_KEYS[r]: m for r, m in ctl.light.rgb.items()},
            "masked": ctl.light.masked,
        },
        "waterfall": {
            "active": ctl.waterfall.left(now) is not None,
            "left_s": _seconds(ctl.waterfall.left(now)),
            "duration": settings.waterfall_duration,
            "schedule": asdict(settings.waterfall_schedule),
        },
        "zaparnik": {"on": ctl.zaparnik.on},
        "alarms": ctl.alarms.snapshot(),
        "energy": dict(ctl.energy),
    }


def build_info(commands) -> dict:
    """Справочник для интерфейса: не меняется во время работы."""
    return {
        "rooms": {ROOM_KEYS[r]: r.value for r in ROOM_KEYS},
        "presets": [
            {"preset": p.value, "title": cfg.PRESET_TITLES[p],
             "setpoints": asdict(cfg.PRESET_SETPOINTS[p])} for p in Preset
        ],
        "zone_kinds": {k.name: k.value for k in ZoneKind},
        "vent_modes": [m.name for m in VentMode],
        "steam_shower_stages": cfg.STEAM_SHOWER_STAGES,
        "rgb_modes": cfg.RGB_MODES,
        "weekdays": list(WEEKDAYS),
        "limits": {
            "zone_setpoint": cfg.ZONE_MAX_SETPOINT,
            "stove_setpoint": cfg.STOVE_MAX_SETPOINT,
            "waterfall_s": cfg.WATERFALL_MAX_S,
        },
        "commands": sorted(commands),
    }


class StatePublisher:
    """Публикует /state при изменениях (не чаще min_interval) и периодически."""

    def __init__(self, ctl: "BathController", min_interval: float = 0.3,
                 period: float = cfg.STATE_PUBLISH_S):
        self.ctl = ctl
        self.min_interval = min_interval
        self.period = period
        self._dirty = True
        self._forced = False
        self._last_at = float("-inf")
        self._last_payload: Optional[str] = None

    def mark_dirty(self) -> None:
        self._dirty = True

    def request(self) -> None:
        self._forced = True

    def maybe_publish(self, now: float) -> None:
        since = now - self._last_at
        periodic = since >= self.period
        if not (periodic or self._forced or (self._dirty and since >= self.min_interval)):
            return
        payload = json.dumps(build_state(self.ctl, now), ensure_ascii=False)
        if payload != self._last_payload or periodic or self._forced:
            self.ctl.gw.publish(TOPIC_STATE, payload, retain=True)
            self._last_payload = payload
        self._last_at = now
        self._dirty = self._forced = False
