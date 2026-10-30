// Свет: бра и RGB-подсветка по комнатам, мастер-клавиша.
window.LightView = (function () {
  "use strict";
  const {h, setText, act} = UI;

  // Цвет образца по включённым каналам (R, G, B) из info.rgb_modes
  const COLORS = {
    "1,1,1": ["#f1efe8", "белый"], "1,0,0": ["#e24b4a", "красный"], "0,1,0": ["#639922", "зелёный"],
    "0,0,1": ["#378add", "синий"], "1,1,0": ["#ef9f27", "жёлтый"], "0,1,1": ["#5dcaa5", "бирюзовый"],
    "1,0,1": ["#d4537e", "пурпурный"],
  };

  function create(el, store) {
    let built = false;
    let cards = [];
    let masked, masterBtn;

    function setLight(room, on) {
      const cur = store.state.light.light;
      const next = {spa: cur.spa, steam: cur.steam};
      next[room] = on;
      return store.send("set_light", next);
    }

    function build(info) {
      const grid = h("div", {class: "grid2"});
      cards = Object.keys(info.rooms).map((room) => {
        const onBtn = h("button", {type: "button"}, "вкл");
        const offBtn = h("button", {type: "button"}, "выкл");
        onBtn.addEventListener("click", () => act(onBtn, setLight(room, true)));
        offBtn.addEventListener("click", () => act(offBtn, setLight(room, false)));
        const swatches = info.rgb_modes.map((rgb, mode) => {
          const c = COLORS[rgb.join(",")];
          const sw = h("button", {
            type: "button",
            class: "swatch" + (c ? "" : " off"),
            style: c ? "background:" + c[0] : null,
            title: c ? c[1] : "выключена",
            "aria-label": "Подсветка: " + (c ? c[1] : "выключена"),
          });
          sw.addEventListener("click", () => act(sw, store.send("set_rgb", {room, mode})));
          return sw;
        });
        const card = h("div", {class: "card"},
          h("div", {class: "card-head"}, h("span", {class: "card-title"}, info.rooms[room]),
            h("span", {class: "row-gap", style: "align-items:center"},
              h("span", {class: "muted"}, "Бра"), h("span", {class: "seg ctl"}, onBtn, offBtn))),
          h("div", {class: "muted", style: "margin:4px 0 10px"}, "Подсветка RGB"),
          h("div", {class: "swatches ctl"}, swatches));
        grid.appendChild(card);
        return {room, onBtn, offBtn, swatches};
      });

      masked = h("div", {class: "card", hidden: true},
        "Свет погашен мастер-клавишей. Повторное нажатие «Мастер» вернёт прежнюю сцену.");
      const nextBtn = h("button", {class: "btn ctl", type: "button"}, "Следующий режим бра");
      nextBtn.addEventListener("click", () => act(nextBtn, store.send("light_next")));
      masterBtn = h("button", {class: "btn ctl", type: "button"}, "Мастер");
      masterBtn.addEventListener("click", () => act(masterBtn, store.send("master")));
      const offBtn = h("button", {class: "btn ctl", type: "button"}, "Выключить весь свет");
      offBtn.addEventListener("click", () => act(offBtn, store.send("all_light_off")));

      el.append(grid, masked, h("div", {class: "row-gap"}, nextBtn, masterBtn, offBtn));
      built = true;
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!built) build(info);
        const l = state.light;
        for (const c of cards) {
          c.onBtn.classList.toggle("on", !!l.light[c.room]);
          c.offBtn.classList.toggle("on", !l.light[c.room]);
          c.swatches.forEach((sw, mode) => sw.classList.toggle("on", l.rgb[c.room] === mode));
        }
        masked.hidden = !l.masked;
        masterBtn.classList.toggle("on", l.masked);
        setText(masterBtn, l.masked ? "Мастер: вернуть свет" : "Мастер");
      },
    };
  }

  return {create};
})();
