import io_config as cfg
from io_config import Preset, Room, ZoneKind

from bath.heating import hysteresis
from bath.gateway import path

HEATER_RELAYS = {z.relay for z in cfg.ALL_ZONES}


def test_startup_everything_off(rig):
    written = {}
    for relay, on in rig.gw.writes:
        written.setdefault(relay, on)
    # на старте вентиляция в «Пропарке», её индикаторы горят
    steaming = {r for room in cfg.VENT_BUTTONS.values()
                for r in room[cfg.VentMode.STEAMING].indicators}
    for relay in cfg.ALL_RELAYS:
        if relay is cfg.R_ALWAYS_ON or relay in steaming:
            continue
        assert written.get(relay) is False, relay.name
    assert rig.on(cfg.R_ALWAYS_ON)
    assert all(rig.on(r) for r in steaming)
    assert rig.ctl.heating.mode == {Room.SPA: Preset.OFF, Room.STEAM: Preset.OFF}


def test_hysteresis():
    assert hysteresis(50, 48, False, 1) is True
    assert hysteresis(50, 49.5, False, 1) is False
    assert hysteresis(50, 49.5, True, 1) is True
    assert hysteresis(50, 51.5, True, 1) is False
    assert hysteresis(0, 10, True, 1) is False
    assert hysteresis(50, None, True, 1) is False


def test_heaters_switch_on_one_by_one(rig):
    rig.temps(20)
    rig.gw.writes.clear()
    rig.cmd(cmd="set_preset", room="steam", preset="russian_bath")
    # команды «вкл» стоят в очереди, на реле ещё ничего не ушло
    assert not [w for w in rig.gw.writes if w[0] in HEATER_RELAYS and w[1]]

    times = []
    for _ in range(400):
        rig.clock.t += 0.01
        before = len(rig.gw.writes)
        rig.gw.flush(rig.now)
        if len(rig.gw.writes) > before:
            times.append(rig.now)
        if not rig.gw.has_pending():
            break
    steam_on = {z.relay for z in cfg.STEAM_ZONES} | {z.relay for z in cfg.STEAM_GEN_GROUP}
    assert {r for r, on in rig.gw.writes if on} == steam_on
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps and min(gaps) >= cfg.HEATER_ON_DELAY_S - 1e-9


def test_off_is_immediate_and_cancels_queue(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="steam", preset="russian_bath")
    rig.gw.flush(rig.now)            # одно реле включилось
    rig.gw.writes.clear()
    rig.cmd(cmd="room_off", room="steam")
    assert not rig.gw.has_pending()
    assert all(on is False for _, on in rig.gw.writes)
    assert rig.gw.writes, "выключение должно уйти сразу"


def test_preset_off_affects_only_its_room(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="spa", preset="SPA")
    rig.cmd(cmd="set_preset", room="steam", preset="steam_bath")
    rig.cmd(cmd="room_off", room="spa")
    rig.flush_all()
    assert not any(rig.on(z.relay) for z in cfg.SPA_ZONES)
    assert all(rig.on(z.relay) for z in cfg.STEAM_ZONES)


def test_spa_ceilings_only_in_pair(rig):
    rig.temps(20)
    c1, c2 = cfg.SPA_CEILING_PAIR
    rig.cmd(cmd="set_preset", room="spa", preset="SPA")   # потолок 58
    rig.flush_all()
    assert rig.on(c1.relay) and rig.on(c2.relay)
    rig.temp(c2, 70)
    rig.advance(1)
    assert not rig.on(c1.relay) and not rig.on(c2.relay)


def test_steam_generator_group_cutoff(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="steam", preset="russian_bath")
    rig.flush_all()
    assert rig.on(cfg.ZONE_EVAPORATOR.relay) and rig.on(cfg.ZONE_STEAM_GENERATOR.relay)
    rig.temp(cfg.ZONE_EVAPORATOR, cfg.STEAM_GEN_MAX_TEMP + 5)
    rig.advance(1)
    assert not rig.on(cfg.ZONE_EVAPORATOR.relay)
    assert not rig.on(cfg.ZONE_STEAM_GENERATOR.relay)
    assert f"overheat:{path(cfg.ZONE_EVAPORATOR.relay)}" in rig.ctl.alarms.active


def test_sensor_error_turns_zone_off(rig):
    rig.temps(20)
    zone = cfg.SPA_ZONES[0]
    rig.cmd(cmd="set_preset", room="spa", preset="beach")
    rig.flush_all()
    assert rig.on(zone.relay)
    rig.event("sensor_error", path(zone.sensor), "r")
    rig.advance(1)
    assert not rig.on(zone.relay)
    assert f"sensor:{path(zone.sensor)}" in rig.ctl.alarms.active
    rig.event("sensor_error", path(zone.sensor), "")
    rig.advance(1)
    rig.flush_all()
    assert rig.on(zone.relay)
    assert f"sensor:{path(zone.sensor)}" not in rig.ctl.alarms.active


def test_stale_sensor_turns_zone_off(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="spa", preset="beach")
    rig.flush_all()
    zone = cfg.SPA_ZONES[0]
    rig.advance(cfg.SENSOR_STALE_S + 1, tick=False)
    for z in cfg.ALL_ZONES:          # все датчики, кроме zone, продолжают слать
        if z is not zone:
            rig.temp(z, 20)
    rig.ctl.tick(rig.now)
    assert not rig.on(zone.relay)
    assert rig.on(cfg.SPA_ZONES[1].relay)


def test_manual_setpoint_applies_immediately_to_all_benches(rig):
    rig.temps(20)
    rig.cmd(cmd="set_manual", room="spa")
    rig.flush_all()
    assert not any(rig.on(z.relay) for z in cfg.SPA_ZONES)
    ack = rig.cmd(cmd="set_manual_setpoint", room="spa", kind="bench", value=45)
    assert ack["ok"]
    rig.flush_all()
    benches = [z for z in cfg.SPA_ZONES if z.kind is ZoneKind.BENCH]
    assert len(benches) == 6 and all(rig.on(z.relay) for z in benches)


def test_manual_setpoint_limits(rig):
    assert not rig.cmd(cmd="set_manual_setpoint", room="spa", kind="bench", value=200)["ok"]
    assert not rig.cmd(cmd="set_manual_setpoint", room="spa", kind="stove", value=100)["ok"]
    assert rig.cmd(cmd="set_manual_setpoint", room="steam", kind="stove", value=300)["ok"]


def test_zaparnik_needs_enable_and_uses_own_sensor(rig):
    rig.temps(20)
    rig.advance(1)
    assert not rig.on(cfg.R_ZAPARNIK_HEAT)
    rig.press(cfg.BTN_ZAPARNIK)
    rig.flush_all()
    assert rig.on(cfg.R_ZAPARNIK_ENABLE) and rig.on(cfg.R_ZAPARNIK_HEAT)
    # датчик тестового блока на запарник не влияет
    rig.event("sensor", path(cfg.T_TEST_BLOCK), 500)
    rig.advance(1)
    assert rig.on(cfg.R_ZAPARNIK_HEAT)
    rig.temp(cfg.ZONE_ZAPARNIK, cfg.ZAPARNIK_SETPOINT + 2)
    rig.advance(1)
    assert not rig.on(cfg.R_ZAPARNIK_HEAT)


def test_settings_saved_but_modes_not_restored(rig, tmp_path):
    from bath.controller import BathController
    from bath.gateway import FakeGateway
    from bath.storage import SettingsStore

    rig.cmd(cmd="set_manual", room="steam")
    rig.cmd(cmd="set_manual_setpoint", room="steam", kind="ceiling", value=70)
    rig.cmd(cmd="waterfall_set_duration", duration=20)
    rig.ctl.shutdown()

    store = SettingsStore(str(tmp_path / "settings.json"))
    ctl = BathController(FakeGateway(), store)
    ctl.start()
    assert store.settings.manual[Room.STEAM].ceiling == 70
    assert store.settings.waterfall_duration == 20
    assert ctl.heating.mode[Room.STEAM] is Preset.OFF


def test_shutdown_turns_heaters_off(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="steam", preset="russian_bath")
    rig.flush_all()
    rig.ctl.shutdown()
    assert not any(rig.on(z.relay) for z in cfg.ALL_ZONES)
