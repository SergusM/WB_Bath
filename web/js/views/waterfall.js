// Обливное: пролив, длительность и расписание.
window.WaterfallView = (function () {
  "use strict";
  const {h, setText, act, mmss} = UI;
  const DAY_TITLES = {mon: "пн", tue: "вт", wed: "ср", thu: "чт", fri: "пт", sat: "сб", sun: "вс"};

  function create(el, store) {
    let built = false;
    let left, ofLabel, pourBtn, stopBtn, slider, sliderOut;
    let enSeg, enOn, enOff, timesEl, dayBtns = {}, saveBtn, resetBtn, dirtyHint, timeInput;
    let draft = null;     // правка расписания, пока не сохранена
    let dirty = false;

    function build(info) {
      left = h("div", {class: "big", style: "font-size:44px"});
      ofLabel = h("div", {class: "muted"});
      // Большая иконка лейки — сама кнопка пролива, как в старой панели
      pourBtn = h("button", {class: "pour-btn ctl", type: "button", "aria-label": "Пролить"},
        h("img", {src: "img/icons/waterfall.png", alt: ""}));
      stopBtn = h("button", {class: "btn ctl", type: "button", style: "min-width:140px"}, "Стоп");
      pourBtn.addEventListener("click", () => act(pourBtn, store.send("waterfall_pour")));
      stopBtn.addEventListener("click", () => act(stopBtn, store.send("waterfall_stop")));

      slider = h("input", {type: "range", min: 1, max: info.limits.waterfall_s, step: 1, class: "ctl",
                           style: "flex:1;width:auto;min-width:0", "aria-label": "Длительность пролива"});
      sliderOut = h("b", {style: "min-width:44px;text-align:right"});
      slider.addEventListener("input", () => setText(sliderOut, slider.value + " с"));
      slider.addEventListener("change", () =>
        act(slider, store.send("waterfall_set_duration", {duration: Number(slider.value)})));

      enOn = h("button", {type: "button"}, "вкл");
      enOff = h("button", {type: "button"}, "выкл");
      enOn.addEventListener("click", () => edit((d) => { d.enabled = true; }));
      enOff.addEventListener("click", () => edit((d) => { d.enabled = false; }));
      enSeg = h("span", {class: "seg ctl"}, enOn, enOff);

      timesEl = h("div", {class: "row-gap ctl"});
      timeInput = h("input", {type: "time", class: "ctl", value: "09:00", "aria-label": "Время пролива"});
      const addBtn = h("button", {class: "btn ctl", type: "button"}, "Добавить");
      addBtn.addEventListener("click", () => {
        const t = timeInput.value;
        if (!t) return;
        edit((d) => { if (!d.times.includes(t)) d.times = d.times.concat(t).sort(); });
      });

      const daysEl = h("div", {class: "row-gap ctl"});
      for (const day of info.weekdays) {
        const b = h("button", {class: "chip", type: "button"}, DAY_TITLES[day] || day);
        b.addEventListener("click", () => edit((d) => {
          d.days = d.days.includes(day) ? d.days.filter((x) => x !== day)
                                        : info.weekdays.filter((x) => x === day || d.days.includes(x));
        }));
        dayBtns[day] = b;
        daysEl.appendChild(b);
      }

      saveBtn = h("button", {class: "btn on ctl", type: "button"}, "Сохранить расписание");
      resetBtn = h("button", {class: "btn ctl", type: "button"}, "Отменить");
      dirtyHint = h("span", {class: "hint"}, "есть несохранённые изменения");
      saveBtn.addEventListener("click", () =>
        act(saveBtn, store.send("waterfall_set_schedule", draft)).then(() => { dirty = false; render(); }));
      resetBtn.addEventListener("click", () => { dirty = false; draft = null; render(); });

      el.append(h("div", {class: "grid2"},
        h("div", {class: "card pour"},
          h("div", {class: "card-title"}, "Пролив"),
          pourBtn, h("div", {class: "hint"}, "нажмите на лейку, чтобы пролить"),
          left, ofLabel, stopBtn,
          h("div", {class: "row-gap", style: "align-items:center;flex-wrap:nowrap;align-self:stretch;margin-top:18px;text-align:left"},
            h("span", {class: "muted"}, "Длительность"), slider, sliderOut)),
        h("div", {class: "card"},
          h("div", {class: "card-head"},
            h("span", {class: "title-row"}, h("img", {class: "card-icon", src: "img/icons/waterfall_dark.png", alt: ""}),
              h("span", {class: "card-title"}, "Расписание")), enSeg),
          h("div", {class: "muted", style: "margin-bottom:8px"}, "Время"), timesEl,
          h("div", {class: "row-gap", style: "margin:10px 0 14px"}, timeInput, addBtn),
          h("div", {class: "muted", style: "margin-bottom:8px"}, "Дни недели"), daysEl,
          h("div", {class: "row-gap", style: "align-items:center;margin-top:16px"}, saveBtn, resetBtn, dirtyHint))));
      built = true;
    }

    function edit(fn) {
      fn(draft);
      dirty = true;
      render();
    }

    function render() {
      const sch = store.state.waterfall.schedule;
      if (!dirty) draft = {enabled: sch.enabled, times: sch.times.slice(), days: sch.days.slice()};
      enOn.classList.toggle("on", draft.enabled);
      enOff.classList.toggle("on", !draft.enabled);
      timesEl.innerHTML = "";
      if (!draft.times.length) timesEl.appendChild(h("span", {class: "hint"}, "время не задано"));
      for (const t of draft.times) {
        const chip = h("button", {class: "chip", type: "button", "aria-label": "Удалить " + t},
          t, h("span", {class: "x"}, "×"));
        chip.addEventListener("click", () => edit((d) => { d.times = d.times.filter((x) => x !== t); }));
        timesEl.appendChild(chip);
      }
      for (const [day, b] of Object.entries(dayBtns)) b.classList.toggle("on", draft.days.includes(day));
      saveBtn.hidden = resetBtn.hidden = dirtyHint.hidden = !dirty;
    }

    return {
      update(state, info) {
        if (!state || !info) return;
        if (!built) build(info);
        const w = state.waterfall;
        setText(left, w.active ? mmss(w.left_s) : w.duration + " с");
        setText(ofLabel, w.active ? "идёт пролив, всего " + w.duration + " с" : "длительность пролива");
        pourBtn.classList.toggle("active", w.active);
        stopBtn.hidden = !w.active;
        if (document.activeElement !== slider) {
          slider.value = w.duration;
          setText(sliderOut, w.duration + " с");
        }
        render();
      },
    };
  }

  return {create};
})();
