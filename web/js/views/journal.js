// Журнал: аварии и счётчик электроэнергии.
window.JournalView = (function () {
  "use strict";
  const {h, setText, act} = UI;

  // Поля state.energy: [подпись, контролы счётчика, единицы, делитель]
  const METRICS = [
    ["Мощность", ["Total P"], "кВт", 1000],
    ["Мощность по фазам", ["P L1", "P L2", "P L3"], "кВт", 1000],
    ["Напряжение", ["Urms L1", "Urms L2", "Urms L3"], "В", 1],
    ["Ток", ["Irms L1", "Irms L2", "Irms L3"], "А", 1],
    ["Энергия", ["Total AP energy"], "кВт·ч", 1],
  ];

  function hhmm(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    const today = new Date().toDateString() === d.toDateString();
    const time = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    return today ? time : d.toLocaleDateString("ru-RU", {day: "numeric", month: "short"}) + " " + time;
  }

  function fmt(v, div) {
    if (v === undefined || v === null || isNaN(v)) return "—";
    const n = Number(v) / div;
    const digits = n >= 100 ? 0 : 1;
    return n.toLocaleString("ru-RU", {minimumFractionDigits: digits, maximumFractionDigits: digits});
  }

  function create(el, store) {
    let built = false;
    let list, ackBtn, metricsEl;

    function build() {
      list = h("div");
      ackBtn = h("button", {class: "btn ctl", type: "button"}, "Подтвердить все");
      ackBtn.addEventListener("click", () => act(ackBtn, store.send("alarms_ack")));
      metricsEl = h("div", {class: "metrics"});
      el.append(
        h("div", {class: "card"},
          h("div", {class: "card-head"}, h("span", {class: "card-title"}, "Аварии"), ackBtn), list),
        h("div", {class: "card"},
          h("div", {class: "card-head"}, h("span", {class: "card-title"}, "Электроэнергия"),
            h("span", {class: "muted"}, "счётчик wb-map3e")), metricsEl));
      built = true;
    }

    return {
      update(state) {
        if (!state) return;
        if (!built) build();
        const a = state.alarms;
        list.innerHTML = "";
        // В history есть и активные аварии: активные сверху, затем по времени
        const items = a.history.slice().sort((x, y) => (x.cleared ? 1 : 0) - (y.cleared ? 1 : 0));
        if (!items.length) list.appendChild(h("div", {class: "muted"}, "Аварий не было."));
        for (const it of items) {
          list.appendChild(h("div", {class: "alarm"},
            h("span", {style: it.acked ? "" : "font-weight:600"}, it.message),
            h("span", {class: "muted"}, hhmm(it.since)),
            h("span", {class: "badge " + (it.cleared ? "cleared" : "active")},
              it.cleared ? "снята " + hhmm(it.cleared) : "активна")));
        }
        ackBtn.hidden = !a.unacked;

        const e = state.energy || {};
        metricsEl.innerHTML = "";
        if (!Object.keys(e).length) {
          metricsEl.appendChild(h("div", {class: "muted"}, "Нет данных счётчика."));
          return;
        }
        for (const [title, keys, unit, div] of METRICS) {
          metricsEl.appendChild(h("div", {class: "metric"},
            h("span", {class: "muted"}, title),
            h("b", {}, keys.map((k) => fmt(e[k], div)).join(" · ") + " " + unit)));
        }
      },
    };
  }

  return {create};
})();
