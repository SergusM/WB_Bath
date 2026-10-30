import json

from bath import io_config as cfg

from bath.api import TOPIC_INFO, TOPIC_STATE

ALL_COMMANDS_OK = [
    dict(cmd="set_preset", room="spa", preset="IR_sauna"),
    dict(cmd="set_manual", room="steam"),
    dict(cmd="set_manual_setpoint", room="steam", kind="FLOOR", value=40),
    dict(cmd="room_off", room="spa"),
    dict(cmd="vent_press", mode="AIRING"),
    dict(cmd="vent_set", mode=1, stage=2),
    dict(cmd="face_fan", on=True),
    dict(cmd="sconce_next"),
    dict(cmd="set_sconce", spa=True, steam=False),
    dict(cmd="rgb_next", room="spa"),
    dict(cmd="set_rgb", room="steam", mode=5),
    dict(cmd="rgb_off", room="steam"),
    dict(cmd="master"),
    dict(cmd="light_off"),
    dict(cmd="waterfall_pour"),
    dict(cmd="waterfall_stop"),
    dict(cmd="waterfall_set_duration", duration=10),
    dict(cmd="waterfall_set_schedule", enabled=True, times=["07:00"], days=["sat", "sun"]),
    dict(cmd="zaparnik", on=True),
    dict(cmd="offoff"),
    dict(cmd="alarms_ack"),
    dict(cmd="get_state"),
]


def test_every_command_accepted(rig):
    names = {c["cmd"] for c in ALL_COMMANDS_OK}
    assert names == set(rig.ctl.api.handlers), "тест должен покрывать все команды"
    for i, c in enumerate(ALL_COMMANDS_OK):
        ack = rig.cmd(id=i, **c)
        assert ack == {"ok": True, "id": i, "cmd": c["cmd"]}, c


def test_bad_commands(rig):
    for payload in ['not json', '[1]', '{"cmd": "nope"}', '{"cmd": "set_preset"}',
                    '{"cmd": "set_preset", "room": "kitchen", "preset": "SPA"}',
                    '{"cmd": "set_rgb", "room": "spa", "mode": 9}']:
        rig.event("cmd", "/app/cmd", payload)
        ack = json.loads([p for p in rig.gw.published if p[0] == "/app/ack"][-1][1])
        assert ack["ok"] is False and ack["error"], payload


def test_state_published(rig):
    rig.temps(30)
    rig.cmd(cmd="set_preset", room="steam", preset="hamam")
    rig.cmd(cmd="vent_set", mode="STEAM_SHOWER", stage=2)
    rig.cmd(cmd="get_state")
    rig.ctl.publisher.maybe_publish(rig.now)
    topic, payload, retain = [p for p in rig.gw.published if p[0] == TOPIC_STATE][-1]
    assert retain
    state = json.loads(payload)
    assert state["heating"]["steam"]["mode"] == "hamam"
    assert state["heating"]["steam"]["setpoints"]["stove"] == 250
    assert state["vent"] == {"mode": "STEAM_SHOWER", "stage": 2, "airing_left_s": None}
    assert len(state["zones"]) == len(cfg.ALL_ZONES)
    assert state["zones"][0]["temp"] == 30


def test_info_published_on_start(rig):
    info = json.loads([p for p in rig.gw.published if p[0] == TOPIC_INFO][0][1])
    assert len(info["presets"]) == len(cfg.Preset)
    assert "set_preset" in info["commands"]
