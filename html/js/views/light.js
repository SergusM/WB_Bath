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
    let masked, masterBtn, masterLabel;

    // Видимое состояние бра: под маской мастер-клавиши лампа погашена
    function lit(room) {
      const l = store.state.light;
      return !!l.light[room] && !l.masked;
    }

    function setLight(room, on) {
      const cur = store.state.light.light;
      const next = {spa: cur.spa, steam: cur.steam};
      next[room] = on;
      return store.send("set_light", next);
    }

    function build(info) {
      const grid = h("div", {class: "grid2"});
      cards = Object.keys(info.rooms).map((room) => {
        const swatches = info.rgb_modes.map((rgb, mode) => {
          const c = COLORS[rgb.join(",")];
          const sw = h("button", {
            type: "button",
            class: "swatch" + (c ? "" : " off"),
            style: c ? "background:" + c[0] + ";--glow:" + c[0] : null,
            title: c ? c[1] : "выключена",
            "aria-label": "Подсветка: " + (c ? c[1] : "выключена"),
          });
          sw.addEventListener("click", () => act(sw, store.send("set_rgb", {room, mode})));
          return sw;
        });
        // Лампа — сама кнопка бра: нажатие включает или гасит, лампа светится
        // или тускнеет вместе с выходом. Лента так же показывает подсветку.
        const bulbImg = h("img", {src: "img/icons/bulb.png", alt: ""});
        const bulbText = h("small");
        const bulb = h("button", {class: "pic-btn ctl", type: "button", "aria-label": "Бра: " + info.rooms[room]},
          bulbImg, h("b", {}, "Бра"), bulbText);
        bulb.addEventListener("click", () => act(bulb, setLight(room, !lit(room))));
        const strip = h("img", {class: "card-icon", src: "img/icons/rgb.png", alt: ""});
        const card = h("div", {class: "card"},
          h("div", {class: "card-head"}, h("span", {class: "card-title"}, info.rooms[room])),
          h("div", {class: "light-room"}, bulb,
            h("div", {class: "device-body"},
              h("div", {class: "title-row", style: "margin-bottom:10px"}, strip,
                h("span", {style: "font-size:16px"}, "Подсветка RGB")),
              h("div", {class: "swatches ctl"}, swatches))));
        grid.appendChild(card);
        return {room, swatches, bulb, bulbImg, bulbText, strip};
      });

      masked = h("div", {class: "card", hidden: true},
        "Свет погашен мастер-клавишей. Повторное нажатие «Мастер» вернёт прежнюю сцену.");
      const iconBtn = (icon, label) => h("button", {class: "icon-btn ctl", type: "button"},
        h("img", {src: "img/icons/" + icon + ".png", alt: ""}), label);
      masterLabel = h("span", {}, "Мастер");
      masterBtn = iconBtn("rgb", masterLabel);
      masterBtn.addEventListener("click", () => act(masterBtn, store.send("master")));
      const offBtn = iconBtn("offoff", "Выключить весь свет");
      offBtn.addEventListener("click", () => act(offBtn, store.send("all_light_off")));

      el.append(grid, masked, h("div", {class: "light-actions"}, masterBtn, offBtn));
      built = true;
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!built) build(info);
        const l = state.light;
        for (const c of cards) {
          c.swatches.forEach((sw, mode) => sw.classList.toggle("on", l.rgb[c.room] === mode));
          const on = lit(c.room);
          c.bulb.classList.toggle("on", on);
          c.bulbImg.classList.toggle("dim", !on);
          setText(c.bulbText, on ? "горит" : "выключено");
          c.strip.classList.toggle("dim", !l.rgb[c.room] || l.masked);
        }
        masked.hidden = !l.masked;
        masterBtn.classList.toggle("on", l.masked);
        setText(masterLabel, l.masked ? "Мастер: вернуть свет" : "Мастер");
      },
    };
  }

  return {create};
})();
