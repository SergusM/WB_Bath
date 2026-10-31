// Нагрев: обе комнаты рядом. В каждой — выбор режима и таблица по поверхностям.
window.HeatingView = (function () {
  "use strict";
  const {h, setText, act, stepper, temp} = UI;
  const MANUAL = "manual";

  function create(el, store) {
    let rooms = null;   // строится по первому state/info: состав зон не меняется

    function build(state, info) {
      el.innerHTML = "";
      const wrap = h("div", {class: "rooms"});
      rooms = Object.keys(info.rooms).map((room) => buildRoom(room, state, info));
      rooms.forEach((r) => wrap.appendChild(r.el));
      el.appendChild(wrap);
      el.appendChild(h("div", {class: "legend hint"},
        h("span", {}, h("span", {class: "cell heat"}, "41"), " греется"),
        h("span", {}, h("span", {class: "cell"}, "43"), " держит температуру"),
        h("span", {}, h("span", {class: "cell bad"}, "—"), " датчик неисправен")));
    }

    function buildRoom(room, state, info) {
      const status = h("span", {class: "muted"});
      const select = h("select", {class: "select ctl", "aria-label": "Режим: " + info.rooms[room]});
      for (const p of info.presets) select.appendChild(h("option", {value: p.preset}, p.title));
      select.appendChild(h("option", {value: MANUAL}, "Ручной"));
      select.addEventListener("change", () => {
        const v = select.value;
        const cmd = v === "off" ? ["room_off", {room}]
                  : v === MANUAL ? ["set_manual", {room}]
                  : ["set_preset", {room, preset: v}];
        act(select, store.send(cmd[0], cmd[1])).catch(() => { select.value = store.state.heating[room].mode; });
      });
      const hint = h("div", {class: "hint mode-hint"});
      const table = h("table", {class: "zones"});

      // Типы поверхностей, у которых в этой комнате есть зоны, в порядке info.zone_kinds
      const kinds = Object.keys(info.zone_kinds).filter((k) =>
        state.zones.some((z) => z.room === room && z.kind === k));
      const rows = kinds.map((kind) => {
        const zones = state.zones.filter((z) => z.room === room && z.kind === kind)
                                 .sort((a, b) => a.index - b.index);
        const stove = kind === "STOVE";
        const value = h("span");
        const step = stepper({
          min: 0,
          max: stove ? info.limits.stove_setpoint : info.limits.zone_setpoint,
          step: stove ? 10 : 1,
          onCommit: (v) => act(null, store.send("set_manual_setpoint", {room, kind, value: v})),
        });
        const cells = zones.map((z) => h("span", {class: "cell", title: z.title}));
        table.appendChild(h("tr", {},
          h("td", {class: "k"}, info.zone_kinds[kind]),
          h("td", {class: "sp"}, value, step.el),
          h("td", {}, h("span", {class: "cells"}, cells))));
        return {kind, field: kind.toLowerCase(), indexes: zones.map((z) => z.index), value, step, cells};
      });

      const card = h("div", {class: "card room"},
        h("div", {class: "card-head"}, h("span", {class: "card-title"}, info.rooms[room]), status),
        select, hint, table);
      return {room, el: card, status, select, hint, rows};
    }

    function updateRoom(r, state, info) {
      const heat = state.heating[r.room];
      const mode = heat.mode;
      const manual = mode === MANUAL;
      const off = mode === "off";
      if (document.activeElement !== r.select && r.select.value !== mode) r.select.value = mode;
      // Фото режима за карточкой, как в старой панели
      const photo = "url(img/modes/" + mode + ".jpg)";
      if (r.photo !== photo) { r.el.style.backgroundImage = photo; r.photo = photo; }
      r.el.classList.toggle("manual", manual);

      const byIndex = new Map(state.zones.map((z) => [z.index, z]));
      const zones = [].concat(...r.rows.map((row) => row.indexes.map((i) => byIndex.get(i))));
      const heating = zones.filter((z) => z && z.heating).length;
      setText(r.status, off ? "выключено" : "греется " + heating + " из " + zones.length);

      const title = (info.presets.find((p) => p.preset === mode) || {}).title;
      setText(r.hint, manual ? "Свои уставки, меняются кнопками − и +. Сохраняются между запусками."
                     : off ? "Нагрев выключен, комната остывает."
                     : "Уставки режима «" + title + "».");

      for (const row of r.rows) {
        const sp = heat.setpoints[row.field];
        row.value.hidden = manual;
        row.step.el.hidden = !manual;
        setText(row.value, off || !sp ? "—" : sp + "°");
        if (manual) row.step.set(heat.manual[row.field]);
        row.indexes.forEach((idx, i) => {
          const z = byIndex.get(idx);
          const cell = row.cells[i];
          const bad = z.status === "error" || z.status === "stale";
          setText(cell, bad ? "—" : temp(z.temp));
          cell.className = "cell" + (bad ? " bad" : z.heating ? " heat" : "");
          cell.title = z.title + (bad ? ": " + (z.status === "stale" ? "нет показаний" : "ошибка датчика") : "");
        });
      }
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!rooms) build(state, info);
        rooms.forEach((r) => updateRoom(r, state, info));
      },
    };
  }

  return {create};
})();
