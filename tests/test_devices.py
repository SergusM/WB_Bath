from datetime import datetime

import io_config as cfg
from io_config import Room, VentMode

STEAM_SHOWER_BTN = cfg.VENT_BUTTONS[Room.SPA][VentMode.STEAM_SHOWER]
AIRING_BTN = cfg.VENT_BUTTONS[Room.STEAM][VentMode.AIRING]


def vent_on(rig):
    return {i for i, r in enumerate(cfg.VENT) if rig.on(r)}


def indicators(rig, mode):
    return [rig.on(r) for room in cfg.VENT_BUTTONS.values() for r in room[mode].indicators]


# --- вентиляция ----------------------------------------------------------------

def test_steam_shower_stages(rig):
    expected = [(0, 4), (1, 4), (2, 4), (3, 4)]
    for stage, pattern in enumerate(expected, 1):
        rig.press(STEAM_SHOWER_BTN)
        assert (rig.ctl.vent.mode, rig.ctl.vent.stage) == (VentMode.STEAM_SHOWER, stage)
        assert vent_on(rig) == set(pattern)
        assert indicators(rig, VentMode.STEAM_SHOWER) == [True, True]
    rig.press(STEAM_SHOWER_BTN)
    assert rig.ctl.vent.mode is VentMode.STEAMING and vent_on(rig) == set()
    assert indicators(rig, VentMode.STEAMING) == [True, True]


def test_airing_auto_return_only_from_airing(rig):
    rig.press(AIRING_BTN)
    assert vent_on(rig) == {3, 5}
    rig.advance(cfg.VENT_AUTO_RETURN_S - 10)
    assert rig.ctl.vent.mode is VentMode.AIRING
    rig.advance(11)
    assert rig.ctl.vent.mode is VentMode.STEAMING

    # «Естественная тяга» и паровой душ сами не сбрасываются
    rig.cmd(cmd="vent_press", mode="NATURAL")
    rig.advance(cfg.VENT_AUTO_RETURN_S * 2)
    assert rig.ctl.vent.mode is VentMode.NATURAL and vent_on(rig) == {4, 5}


def test_vent_set_from_ui(rig):
    assert rig.cmd(cmd="vent_set", mode="STEAM_SHOWER", stage=3)["ok"]
    assert vent_on(rig) == {2, 4}
    assert not rig.cmd(cmd="vent_set", mode="STEAM_SHOWER", stage=5)["ok"]


def test_face_fan_auto_off(rig):
    rig.press(cfg.BTN_FACE_FAN)
    assert all(rig.on(r) for r in cfg.BTN_FACE_FAN.indicators)
    rig.advance(cfg.FACE_FAN_AUTO_OFF_S + 1)
    assert not any(rig.on(r) for r in cfg.BTN_FACE_FAN.indicators)
    rig.cmd(cmd="face_fan", on=True)
    assert rig.on(cfg.R_FACE_FAN)
    rig.cmd(cmd="face_fan")
    assert not rig.on(cfg.R_FACE_FAN)


# --- свет ----------------------------------------------------------------------

def rgb(rig, room):
    from bath.lighting import RGB_RELAYS
    return tuple(int(rig.on(r)) for r in RGB_RELAYS[room])


def test_sconce_cycle(rig):
    seen = []
    for _ in range(4):
        rig.press(cfg.BTN_SCONCE)
        seen.append((int(rig.on(cfg.R_SCONCE_SPA)), int(rig.on(cfg.R_SCONCE_STEAM))))
    assert seen == cfg.SCONCE_MODES[1:] + cfg.SCONCE_MODES[:1]


def test_rgb_short_and_long_press(rig):
    rig.press(cfg.BTN_RGB_SPA)
    assert rgb(rig, Room.SPA) == cfg.RGB_MODES[1]
    rig.press(cfg.BTN_RGB_SPA)
    assert rgb(rig, Room.SPA) == cfg.RGB_MODES[2]
    rig.press(cfg.BTN_RGB_SPA, hold=cfg.LONG_PRESS_RGB_S + 0.1)
    assert rgb(rig, Room.SPA) == (0, 0, 0)
    assert rgb(rig, Room.STEAM) == (0, 0, 0)


def test_rgb_cycle_skips_off(rig):
    for _ in range(len(cfg.RGB_MODES) - 1):
        rig.cmd(cmd="rgb_next", room="steam")
    assert rig.ctl.light.rgb[Room.STEAM] == 7
    rig.cmd(cmd="rgb_next", room="steam")
    assert rig.ctl.light.rgb[Room.STEAM] == 1


def test_master_key(rig):
    rig.press(cfg.BTN_MASTER)                      # всё было выкл -> включить всё
    assert rig.on(cfg.R_SCONCE_SPA) and rig.on(cfg.R_SCONCE_STEAM)
    assert rgb(rig, Room.SPA) == (1, 1, 1)
    rig.cmd(cmd="set_rgb", room="steam", mode=4)
    rig.press(cfg.BTN_MASTER)                      # погасить, сцену запомнить
    assert not rig.on(cfg.R_SCONCE_SPA) and rgb(rig, Room.STEAM) == (0, 0, 0)
    assert rig.ctl.light.masked
    rig.press(cfg.BTN_MASTER)                      # вернуть сцену
    assert rig.on(cfg.R_SCONCE_SPA) and rgb(rig, Room.STEAM) == (0, 0, 1)


def test_master_long_press_offoff(rig):
    rig.temps(20)
    rig.cmd(cmd="set_preset", room="steam", preset="steam_bath")
    rig.cmd(cmd="sconce_next")
    rig.cmd(cmd="vent_press", mode="NATURAL")
    rig.flush_all()
    rig.press(cfg.BTN_MASTER, hold=cfg.LONG_PRESS_MASTER_S + 0.1)
    assert not any(rig.on(r) for r in cfg.LIGHT_RELAYS)
    assert not any(rig.on(z.relay) for z in cfg.ALL_ZONES)
    assert rig.ctl.vent.mode is VentMode.NATURAL      # вентиляцию offoff не трогает


# --- обливное ------------------------------------------------------------------

def test_waterfall_exact_duration(rig):
    rig.cmd(cmd="waterfall_set_duration", duration=30)
    rig.press(cfg.BTN_WATERFALL)
    assert rig.on(cfg.R_WATERFALL)
    rig.advance(29)
    assert rig.on(cfg.R_WATERFALL)
    rig.advance(1.1)
    assert not rig.on(cfg.R_WATERFALL)


def test_waterfall_pour_from_ui_and_stop(rig):
    assert rig.cmd(cmd="waterfall_pour", duration=5)["ok"]
    assert rig.on(cfg.R_WATERFALL)
    rig.cmd(cmd="waterfall_stop")
    assert not rig.on(cfg.R_WATERFALL)
    assert not rig.cmd(cmd="waterfall_pour", duration=999)["ok"]


def test_waterfall_schedule_after_midnight_once_per_minute(rig):
    assert rig.cmd(cmd="waterfall_set_schedule", enabled=True,
                   times=["0:30"], days=["tue"])["ok"]
    rig.wall.dt = datetime(2026, 10, 27, 0, 30, 5)    # вторник 00:30
    rig.advance(1)
    assert rig.on(cfg.R_WATERFALL)
    rig.ctl.waterfall.stop()
    rig.wall.dt = datetime(2026, 10, 27, 0, 30, 30)
    rig.advance(1)
    assert not rig.on(cfg.R_WATERFALL)                # в ту же минуту повторно не льёт
    rig.wall.dt = datetime(2026, 10, 28, 0, 30, 0)    # среда — не по расписанию
    rig.advance(1)
    assert not rig.on(cfg.R_WATERFALL)
