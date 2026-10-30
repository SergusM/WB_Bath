// Состояние интерфейса: последние /app/state и /app/info, статус связи,
// отправка команд с ожиданием /app/ack.
window.Store = class Store {
  constructor(transport, cfg) {
    this.transport = transport;
    this.cfg = cfg;
    this.state = null;
    this.info = null;
    this.online = null;       // /app/online: true, false или null — ещё не знаем
    this.linked = false;      // есть соединение с брокером
    this.lastStateAt = 0;
    this.pending = new Map(); // id команды → {resolve, reject, timer}
    this.listeners = [];
    this.seq = 0;
  }

  subscribe(fn) {
    this.listeners.push(fn);
  }

  notify(what) {
    for (const fn of this.listeners) fn(what);
  }

  start() {
    this.transport.start(
      (sub, text) => this.onMessage(sub, text),
      (linked) => { this.linked = linked; this.notify("link"); });
    // Статус «не в сети» зависит от времени, а не только от сообщений
    setInterval(() => this.notify("link"), 5000);
  }

  // broker — нет соединения с брокером; offline — контроллер молчит; online
  link() {
    if (!this.linked) return "broker";
    if (this.online === false || !this.state) return "offline";
    if (Date.now() - this.lastStateAt > this.cfg.offlineAfterMs) return "offline";
    return "online";
  }

  onMessage(sub, text) {
    if (sub === "state" || sub === "info") {
      try {
        this[sub] = JSON.parse(text);
      } catch (e) {
        return;
      }
      if (sub === "state") this.lastStateAt = Date.now();
      this.notify(sub);
    } else if (sub === "online") {
      this.online = text.trim() === "1";
      this.notify("link");
    } else if (sub === "ack") {
      this.onAck(text);
    } else if (sub === "event") {
      try {
        const ev = JSON.parse(text);
        if (ev.type === "alarm") UI.toast("Авария: " + ev.message, "error");
      } catch (e) { /* не JSON — не наше */ }
    }
  }

  onAck(text) {
    let ack;
    try { ack = JSON.parse(text); } catch (e) { return; }
    const p = this.pending.get(ack.id);
    if (!p) return;   // ответ на команду другого клиента
    this.pending.delete(ack.id);
    clearTimeout(p.timer);
    if (ack.ok) p.resolve(ack);
    else p.reject(new Error(ack.error || "Команда отклонена"));
  }

  // Отправка команды → Promise, который ждёт /app/ack с тем же id
  send(cmd, args) {
    if (this.link() !== "online") return Promise.reject(new Error("Нет связи с контроллером"));
    const id = "ui-" + Date.now().toString(36) + "-" + (++this.seq);
    const msg = Object.assign({cmd, id}, args || {});
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Контроллер не ответил на команду"));
      }, this.cfg.ackTimeoutMs);
      this.pending.set(id, {resolve, reject, timer});
      this.transport.publish("cmd", JSON.stringify(msg));
    });
  }
};
