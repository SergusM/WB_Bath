"""Снимки /app/state и /app/info для демо-режима веб-интерфейса (html/?demo).

Поднимает настоящий BathController на FakeGateway, задаёт правдоподобные
температуры и режимы и сохраняет то, что контроллер опубликовал бы в MQTT:

    python tools/gen_web_demo.py

Перезапускайте после изменения состава state/info в bath/api.py.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bath import io_config as cfg  # noqa: E402
from bath.api import build_info, build_state  # noqa: E402
from bath.controller import BathController  # noqa: E402
from bath.gateway import Event, FakeGateway, path  # noqa: E402
from bath.storage import SettingsStore  # noqa: E402

OUT_DIR = os.path.join(ROOT, "html", "demo")

# Температура зоны по типу поверхности: часть зон ниже уставки (греются),
# часть выше (держат)
TEMPS = {
    cfg.ZoneKind.FLOOR: 39, cfg.ZoneKind.BENCH: 41, cfg.ZoneKind.WALL_LOW: 50,
    cfg.ZoneKind.WALL_MID: 63, cfg.ZoneKind.WALL_TOP: 77, cfg.ZoneKind.CEILING: 74,
    cfg.ZoneKind.STOVE: 385,
}
BENCH_SPREAD = [0, 3, -1, 2, 0, 4]
ENERGY = {
    "Total P": 18420, "P L1": 6110, "P L2": 6290, "P L3": 6020,
    "Urms L1": 228.4, "Urms L2": 231.1, "Urms L3": 229.0,
    "Irms L1": 26.7, "Irms L2": 27.2, "Irms L3": 26.3,
    "Total AP energy": 12840.6, "AP energy L1": 4301.2, "AP energy L2": 4288.9,
    "AP energy L3": 4250.5,
}


def main() -> None:
    t = [1000.0]
    wall = [datetime(2026, 10, 30, 18, 5)]
    store = SettingsStore(os.path.join(tempfile.mkdtemp(), "settings.json"))
    ctl = BathController(FakeGateway(), store, clock=lambda: t[0], wallclock=lambda: wall[0])
    ctl.start()

    def send(kind, key, value):
        ctl.handle(Event(kind, key, value), t[0])

    def temp(zone, value):
        send("sensor", path(zone.sensor), value - zone.sensor.correction)

    def cmd(**data):
        send("cmd", "/app/cmd", json.dumps(data))

    benches = 0
    for zone in cfg.ALL_ZONES:
        if zone is cfg.ZONE_ZAPARNIK:
            temp(zone, 118)
        elif zone.kind is cfg.ZoneKind.BENCH:
            temp(zone, TEMPS[zone.kind] + BENCH_SPREAD[benches % len(BENCH_SPREAD)])
            benches += 1
        else:
            temp(zone, TEMPS[zone.kind])
    send("sensor", path(cfg.T_TEST_BLOCK), 24)
    for c in cfg.ENERGY_METER:
        send("energy", path(c), ENERGY[c.control])

    # История аварий: перегрев испарителя, который уже снят
    temp(cfg.ZONE_EVAPORATOR, cfg.STEAM_GEN_MAX_TEMP + 2)
    ctl.tick(t[0])
    wall[0] = datetime(2026, 10, 30, 18, 7)
    temp(cfg.ZONE_EVAPORATOR, TEMPS[cfg.ZoneKind.STOVE])
    ctl.tick(t[0])

    # Активная авария: ошибка датчика пятого лежака СПА
    wall[0] = datetime(2026, 10, 30, 19, 31)
    send("sensor_error", path(cfg.SPA_ZONES[4].sensor), "r")

    for name, value in (("floor", 40), ("bench", 45), ("wall_low", 50), ("wall_mid", 60),
                        ("wall_top", 70), ("ceiling", 75), ("stove", 400)):
        cmd(cmd="set_manual_setpoint", room="steam", kind=name, value=value)
    cmd(cmd="set_preset", room="spa", preset="SPA")
    cmd(cmd="set_preset", room="steam", preset="russian_bath")
    cmd(cmd="vent_set", mode="STEAM_SHOWER", stage=2)
    cmd(cmd="set_light", spa=True, steam=False)
    cmd(cmd="set_rgb", room="spa", mode=4)
    cmd(cmd="zaparnik", on=True)
    cmd(cmd="waterfall_set_schedule", enabled=True, times=["09:00", "21:30"],
        days=["mon", "tue", "wed", "thu", "fri"])
    t[0] += 1
    ctl.tick(t[0])

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, data in (("state", build_state(ctl, t[0])),
                       ("info", build_info(ctl.api.handlers))):
        with open(os.path.join(OUT_DIR, f"{name}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
    print(f"Записаны {os.path.relpath(OUT_DIR, ROOT)}/state.json и info.json")


if __name__ == "__main__":
    main()
