// Климат: вентиляция (общая на обе комнаты), лицевой фен, запарник.
window.ClimateView = (function () {
  "use strict";
  const {h, setText, act, mmss, temp} = UI;

  // Подпись режима и металлическая кнопка, у которой во включённом
  // состоянии горит кольцо своего цвета (как в старой панели)
  const MODES = {
    STEAMING: ["Пропарка", "knob1"],
    STEAM_SHOWER: ["Паровой душ", "knob2"],
    NATURAL: ["Естественная тяга", "knob3"],
    AIRING: ["Проветривание", "knob4"],
  };
  const KNOB_OFF = "img/icons/knob_off.png";

  function create(el, store) {
    let built = false;
    const knobs = {};
    let fan, zap;

    // Устройство включается и выключается нажатием на его картинку,
    // как лампа бра. Справа — состояние и подробности.
    function device(title, src, onClick) {
      const img = h("img", {src, alt: ""});
      const pic = h("button", {class: "pic-btn ctl", type: "button", "aria-label": title}, img);
      const value = h("div", {class: "big"});
      const info = h("div", {class: "muted"});
      pic.addEventListener("click", () => act(pic, onClick()));
      const card = h("div", {class: "card"},
        h("div", {class: "card-head"}, h("span", {class: "card-title"}, title)),
        h("div", {class: "device"}, pic, h("div", {class: "device-body"}, value, info)));
      return {card, pic, img, value, info};
    }

    function setDevice(d, on, value, info) {
      d.pic.classList.toggle("on", on);
      d.img.classList.toggle("dim", !on);
      setText(d.value, value);
      setText(d.info, info);
    }

    function build(info) {
      const knobsEl = h("div", {class: "knobs"});
      for (const mode of info.vent_modes) {
        const [title, img] = MODES[mode] || [mode, "knob1"];
        const image = h("img", {src: KNOB_OFF, alt: ""});
        const stage = h("span", {class: "knob-stage", hidden: true});
        const sub = h("small");
        const knob = h("button", {class: "knob ctl", type: "button"},
          h("span", {class: "knob-face"}, image, stage), h("b", {}, title), sub);
        // Как физическая кнопка: повторное нажатие «Парового душа»
        // переключает ступень 1→2→3→4→пропарка, это решает контроллер
        knob.addEventListener("click", () => act(knob, store.send("vent_press", {mode})));
        knobs[mode] = {knob, image, stage, sub, on: "img/icons/" + img + ".png"};
        knobsEl.appendChild(knob);
      }

      fan = device("Лицевой фен", "img/icons/vent.png",
        () => store.send("face_fan", {on: !store.state.face_fan.on}));
      zap = device("Запарник", "img/modes/steam_bath.jpg",
        () => store.send("zaparnik", {on: !store.state.zaparnik.on}));

      el.append(h("div", {class: "climate"},
        h("div", {class: "card"},
          h("div", {class: "card-head"},
            h("span", {class: "title-row"}, h("img", {class: "card-icon", src: "img/icons/vent.png", alt: ""}),
              h("span", {class: "card-title"}, "Вентиляция")),
            h("span", {class: "muted"}, "общая на СПА и парную")),
          knobsEl),
        h("div", {class: "climate-side"},
          fan.card, zap.card)));
      built = true;
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!built) build(info);
        const v = state.vent;
        for (const [mode, k] of Object.entries(knobs)) {
          const on = v.mode === mode;
          k.knob.classList.toggle("on", on);
          const src = on ? k.on : KNOB_OFF;
          if (k.image.getAttribute("src") !== src) k.image.setAttribute("src", src);
          const shower = mode === "STEAM_SHOWER";
          k.stage.hidden = !(shower && on);
          setText(k.stage, String(v.stage));
          setText(k.sub, shower ? (on ? "скорость " + v.stage + " из " + info.steam_shower_stages
                                      : "нажатие — следующая скорость")
                       : mode === "AIRING" ? (on ? "пропарка через " + mmss(v.airing_left_s) : "15 минут")
                       : mode === "STEAMING" ? "всё закрыто" : "");
        }

        const f = state.face_fan;
        setDevice(fan, f.on, f.on ? "Включён" : "Выключен",
                  f.on ? "выключится через " + mmss(f.left_s) : "нажмите на картинку, чтобы включить");

        // Зона запарника — единственная без комнаты
        const z = state.zones.find((x) => !x.room);
        const zOn = state.zaparnik.on;
        setDevice(zap, zOn, z ? temp(z.temp) + "°" : "—",
                  zOn ? "цель " + z.setpoint + "° · " + (z.heating ? "греется" : "держит")
                      : "выключен, нажмите на картинку");
      },
    };
  }

  return {create};
})();
