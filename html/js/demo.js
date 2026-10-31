// Демо-режим (index.html?demo): без брокера и контроллера.
// Берёт снимки demo/info.json и demo/state.json (tools/gen_web_demo.py) и
// упрощённо изображает контроллер: отвечает на команды и меняет состояние.
// Это не копия логики bath/, а заглушка для разработки интерфейса.
window.DemoTransport = class DemoTransport {
  start(onMessage, onLink) {
    this.emit = onMessage;
    Promise.all(["demo/info.json", "demo/state.json"].map((u) => fetch(u).then((r) => r.json())))
      .then(([info, state]) => {
        this.info = info;
        this.state = state;
        onLink(true);
        this.emit("online", "1");
        this.emit("info", JSON.stringify(info));
        this.push();
        setInterval(() => this.second(), 1000);
      })
      .catch((e) => {
        onLink(false);
        UI.toast("Демо: не удалось загрузить demo/*.json (" + e.message + ")", "error");
      });
  }

  push() {
    this.emit("state", JSON.stringify(this.state));
  }

  publish(sub, text) {
    if (sub !== "cmd") return;
    const d = JSON.parse(text);
    let ack = {ok: true};
    try {
      this.apply(d);
    } catch (e) {
      ack = {ok: false, error: e.message};
    }
    setTimeout(() => {
      this.emit("ack", JSON.stringify(Object.assign(ack, {id: d.id, cmd: d.cmd})));
      this.push();
    }, 150);
  }

  apply(d) {
    const s = this.state, info = this.info;
    const room = d.room;
    const preset = (key) => info.presets.find((p) => p.preset === key);
    switch (d.cmd) {
      case "set_preset":
        s.heating[room].mode = d.preset;
        s.heating[room].setpoints = Object.assign({}, preset(d.preset).setpoints);
        break;
      case "room_off":
        s.heating[room].mode = "off";
        s.heating[room].setpoints = Object.assign({}, preset("off").setpoints);
        break;
      case "set_manual":
        s.heating[room].mode = "manual";
        s.heating[room].setpoints = Object.assign({}, s.heating[room].manual);
        break;
      case "set_manual_setpoint": {
        const stove = d.kind === "STOVE";
        const limit = stove ? info.limits.stove_setpoint : info.limits.zone_setpoint;
        if (stove && room !== "steam") throw new Error("печка есть только в парной");
        if (!(d.value >= 0 && d.value <= limit)) throw new Error("уставка должна быть от 0 до " + limit);
        s.heating[room].manual[d.kind.toLowerCase()] = d.value;
        if (s.heating[room].mode === "manual") s.heating[room].setpoints[d.kind.toLowerCase()] = d.value;
        break;
      }
      case "vent_press":
        if (d.mode === "STEAM_SHOWER") {
          const st = s.vent.mode === "STEAM_SHOWER" ? s.vent.stage + 1 : 1;
          s.vent = st > info.steam_shower_stages ? {mode: "STEAMING", stage: 0, airing_left_s: null}
                                                 : {mode: "STEAM_SHOWER", stage: st, airing_left_s: null};
        } else {
          s.vent = {mode: d.mode, stage: 0, airing_left_s: d.mode === "AIRING" ? 900 : null};
        }
        break;
      case "vent_set":
        s.vent = {mode: d.mode, stage: d.mode === "STEAM_SHOWER" ? (d.stage || 1) : 0,
                  airing_left_s: d.mode === "AIRING" ? 900 : null};
        break;
      case "face_fan": {
        const on = d.on === undefined || d.on === null ? !s.face_fan.on : d.on;
        s.face_fan = {on, left_s: on ? 900 : null};
        break;
      }
      case "zaparnik":
        s.zaparnik.on = d.on === undefined || d.on === null ? !s.zaparnik.on : d.on;
        break;
      case "light_next": {
        const modes = [[false, false], [true, true], [true, false], [false, true]];
        const i = modes.findIndex((m) => m[0] === s.light.light.spa && m[1] === s.light.light.steam);
        const m = modes[(i + 1) % modes.length];
        s.light.light = {spa: m[0], steam: m[1]};
        s.light.masked = false;
        break;
      }
      case "set_light":
        s.light.light = {spa: !!d.spa, steam: !!d.steam};
        s.light.masked = false;
        break;
      case "set_rgb":
        if (!(d.mode >= 0 && d.mode < info.rgb_modes.length)) throw new Error("режим RGB должен быть от 0 до 7");
        s.light.rgb[room] = d.mode;
        s.light.masked = false;
        break;
      case "master":
        s.light.masked = !s.light.masked;
        break;
      case "all_light_off":
        s.light = {light: {spa: false, steam: false}, rgb: {spa: 0, steam: 0}, masked: false};
        break;
      case "waterfall_pour":
        s.waterfall.active = true;
        s.waterfall.left_s = d.duration || s.waterfall.duration;
        break;
      case "waterfall_stop":
        s.waterfall.active = false;
        s.waterfall.left_s = null;
        break;
      case "waterfall_set_duration":
        if (!(d.duration >= 1 && d.duration <= info.limits.waterfall_s)) {
          throw new Error("длительность должна быть от 1 до " + info.limits.waterfall_s + " с");
        }
        s.waterfall.duration = d.duration;
        break;
      case "waterfall_set_schedule":
        Object.assign(s.waterfall.schedule, {enabled: d.enabled, times: d.times.slice().sort(), days: d.days});
        break;
      case "offoff":
        for (const r of ["spa", "steam"]) this.apply({cmd: "room_off", room: r});
        this.apply({cmd: "all_light_off"});
        s.zaparnik.on = false;
        s.face_fan = {on: false, left_s: null};
        s.waterfall.active = false;
        s.waterfall.left_s = null;
        break;
      case "alarms_ack":
        s.alarms.history.forEach((a) => { a.acked = true; });
        s.alarms.active.forEach((a) => { a.acked = true; });
        s.alarms.unacked = 0;
        break;
      case "get_state":
        break;
      default:
        throw new Error("неизвестная команда " + d.cmd);
    }
    this.recalc();
  }

  // Уставки и признак нагрева зон по режиму комнаты
  recalc() {
    const s = this.state;
    for (const z of s.zones) {
      if (z.room && z.kind) z.setpoint = s.heating[z.room].setpoints[z.kind.toLowerCase()];
      else if (!z.room) z.setpoint = s.zaparnik.on ? 130 : 0;
      z.heating = z.temp !== null && z.setpoint > 0 && z.temp < z.setpoint;
    }
  }

  second() {
    const s = this.state;
    let changed = false;
    const down = (obj, key, onZero) => {
      if (obj[key] === null) return;
      obj[key] -= 1;
      changed = true;
      if (obj[key] <= 0) onZero();
    };
    down(s.waterfall, "left_s", () => { s.waterfall.active = false; s.waterfall.left_s = null; });
    down(s.face_fan, "left_s", () => { s.face_fan = {on: false, left_s: null}; });
    down(s.vent, "airing_left_s", () => { s.vent = {mode: "STEAMING", stage: 0, airing_left_s: null}; });
    if (changed) this.push();
  }
};
