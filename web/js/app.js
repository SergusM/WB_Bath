// Запуск интерфейса: транспорт, store, разделы, навигация, шапка.
(function () {
  "use strict";
  const {setText, confirm, act, plural} = UI;
  const cfg = window.BATH_CONFIG;
  const demo = new URLSearchParams(location.search).has("demo");
  const store = new Store(demo ? new DemoTransport() : new MqttTransport(cfg), cfg);

  const views = {
    heat: HeatingView.create(document.getElementById("view-heat"), store),
    climate: ClimateView.create(document.getElementById("view-climate"), store),
    light: LightView.create(document.getElementById("view-light"), store),
    water: WaterfallView.create(document.getElementById("view-water"), store),
    journal: JournalView.create(document.getElementById("view-journal"), store),
  };

  // --- навигация по #разделу -----------------------------------------------

  function route() {
    const name = (location.hash || "#heat").slice(1);
    const current = views[name] ? name : "heat";
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === current));
    document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === current));
  }
  window.addEventListener("hashchange", route);
  route();

  // --- шапка ----------------------------------------------------------------

  const app = document.getElementById("app");
  const linkText = document.getElementById("link-text");
  const badge = document.getElementById("alarm-badge");
  const LINK_TEXT = {
    broker: "нет связи с брокером",
    offline: "контроллер не в сети",
    online: demo ? "демо-режим" : "в сети",
  };

  function renderLink() {
    const link = store.link();
    app.dataset.link = link;
    setText(linkText, LINK_TEXT[link]);
  }

  function renderBadge(state) {
    const active = state.alarms.active.length;
    const unacked = state.alarms.unacked;
    badge.hidden = !active && !unacked;
    setText(badge, active ? active + " " + plural(active, "авария", "аварии", "аварий")
                          : unacked + " " + plural(unacked, "новая запись", "новые записи", "новых записей"));
  }
  badge.addEventListener("click", () => { location.hash = "#journal"; });

  const clock = document.getElementById("clock");
  function tickClock() {
    const d = new Date();
    setText(clock, d.toLocaleDateString("ru-RU", {weekday: "short", day: "numeric", month: "short"}) +
      " · " + d.toLocaleTimeString("ru-RU", {hour: "2-digit", minute: "2-digit"}));
  }
  setInterval(tickClock, 10000);
  tickClock();

  const offoff = document.getElementById("offoff");
  offoff.addEventListener("click", () => {
    confirm("Выключить нагрев, свет, лицевой фен, запарник и обливное? Вентиляция останется как есть.",
            "Выключить всё").then((yes) => {
      if (yes) act(offoff, store.send("offoff")).catch(() => {});
    });
  });

  // --- обновления -----------------------------------------------------------

  store.subscribe((what) => {
    renderLink();
    if (what !== "state" && what !== "info") return;
    document.getElementById("waiting").hidden = !!(store.state && store.info);
    if (store.state) renderBadge(store.state);
    for (const v of Object.values(views)) v.update(store.state, store.info);
  });
  store.start();
})();
