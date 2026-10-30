// Климат: вентиляция (общая на обе комнаты), лицевой фен, запарник.
window.ClimateView = (function () {
  "use strict";
  const {h, setText, act, mmss, temp} = UI;

  const MODES = {
    STEAMING: "Пропарка",
    STEAM_SHOWER: "Паровой душ",
    NATURAL: "Естественная тяга",
    AIRING: "Проветривание",
  };

  function create(el, store) {
    let built = false;
    const tiles = {};
    let stageSeg, stageWrap, stageBtns = [];
    let fanState, fanLeft, fanBtn, zapTemp, zapInfo, zapBtn;

    function build(info) {
      const tilesEl = h("div", {class: "tiles"});
      for (const mode of info.vent_modes) {
        const sub = h("small");
        const tile = h("button", {class: "tile ctl", type: "button"}, h("span", {}, MODES[mode] || mode), sub);
        tile.addEventListener("click", () => {
          const s = store.state.vent;
          if (mode === "STEAM_SHOWER") {
            if (s.mode !== mode) act(tile, store.send("vent_set", {mode, stage: 1}));
          } else {
            act(tile, store.send("vent_press", {mode}));
          }
        });
        tiles[mode] = {tile, sub};
        tilesEl.appendChild(tile);
      }
      stageSeg = h("span", {class: "seg ctl"});
      for (let i = 1; i <= info.steam_shower_stages; i++) {
        const b = h("button", {type: "button"}, String(i));
        b.addEventListener("click", () => act(b, store.send("vent_set", {mode: "STEAM_SHOWER", stage: i})));
        stageBtns.push(b);
        stageSeg.appendChild(b);
      }
      stageWrap = h("div", {class: "row-gap", style: "align-items:center;margin-top:12px"},
        h("span", {class: "muted"}, "Ступень парового душа"), stageSeg);

      fanState = h("span", {class: "big"});
      fanLeft = h("span", {class: "muted"});
      fanBtn = h("button", {class: "btn wide ctl", type: "button", style: "margin-top:12px"});
      fanBtn.addEventListener("click", () =>
        act(fanBtn, store.send("face_fan", {on: !store.state.face_fan.on})));

      zapTemp = h("span", {class: "big"});
      zapInfo = h("span", {class: "muted"});
      zapBtn = h("button", {class: "btn wide ctl", type: "button", style: "margin-top:12px"});
      zapBtn.addEventListener("click", () =>
        act(zapBtn, store.send("zaparnik", {on: !store.state.zaparnik.on})));

      el.append(
        h("div", {class: "card"},
          h("div", {class: "card-head"}, h("span", {class: "card-title"}, "Вентиляция"),
            h("span", {class: "muted"}, "общая на СПА и парную")),
          tilesEl, stageWrap),
        h("div", {class: "grid2"},
          h("div", {class: "card"},
            h("div", {class: "card-head"}, h("span", {class: "card-title"}, "Лицевой фен"), fanLeft),
            fanState, fanBtn),
          h("div", {class: "card"},
            h("div", {class: "card-head"}, h("span", {class: "card-title"}, "Запарник"), zapInfo),
            zapTemp, zapBtn)));
      built = true;
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!built) build(info);
        const v = state.vent;
        for (const [mode, t] of Object.entries(tiles)) {
          t.tile.classList.toggle("on", v.mode === mode);
          setText(t.sub, mode === "STEAM_SHOWER" ? (v.mode === mode ? "ступень " + v.stage : "ступени 1–" + info.steam_shower_stages)
                       : mode === "AIRING" ? (v.mode === mode ? "пропарка через " + mmss(v.airing_left_s) : "15 минут")
                       : mode === "STEAMING" ? "всё закрыто" : "");
        }
        stageWrap.hidden = v.mode !== "STEAM_SHOWER";
        stageBtns.forEach((b, i) => b.classList.toggle("on", v.stage === i + 1));

        const fan = state.face_fan;
        setText(fanState, fan.on ? "Включён" : "Выключен");
        setText(fanLeft, fan.on ? "выключится через " + mmss(fan.left_s) : "");
        setText(fanBtn, fan.on ? "Выключить" : "Включить");

        // Зона запарника — единственная без комнаты
        const zap = state.zones.find((z) => !z.room);
        const zapOn = state.zaparnik.on;
        setText(zapTemp, zap ? temp(zap.temp) + "°" : "—");
        setText(zapInfo, !zapOn ? "выключен" : "цель " + zap.setpoint + "° · " + (zap.heating ? "греется" : "держит"));
        setText(zapBtn, zapOn ? "Выключить" : "Включить");
      },
    };
  }

  return {create};
})();
