// Связь с брокером WB по MQTT over WebSocket (mqtt.js из vendor/).
// Интерфейс транспорта: start(onMessage(sub, text), onLink(bool)), publish(sub, text).
// sub — топик без префикса: "state", "info", "ack", "event", "online".
window.MqttTransport = class MqttTransport {
  constructor(cfg) {
    const param = new URLSearchParams(location.search).get("mqtt");
    const host = location.hostname || "localhost";
    this.url = param || cfg.mqttUrl || "ws://" + host + ":" + cfg.mqttPort + "/mqtt";
    this.prefix = cfg.prefix;
    this.client = null;
  }

  start(onMessage, onLink) {
    if (!window.mqtt) {
      onLink(false);
      UI.toast("Нет библиотеки vendor/mqtt.min.js, связь с брокером невозможна", "error");
      return;
    }
    const prefix = this.prefix;
    this.client = window.mqtt.connect(this.url, {
      clientId: "bath-ui-" + Math.random().toString(16).slice(2, 10),
      reconnectPeriod: 3000,
      connectTimeout: 5000,
      clean: true,
    });
    this.client.on("connect", () => {
      this.client.subscribe(prefix + "/#");
      onLink(true);
    });
    for (const ev of ["close", "offline", "error"]) {
      this.client.on(ev, () => onLink(false));
    }
    this.client.on("message", (topic, payload) => {
      if (topic.startsWith(prefix + "/")) onMessage(topic.slice(prefix.length + 1), payload.toString());
    });
  }

  publish(sub, text) {
    if (this.client) this.client.publish(this.prefix + "/" + sub, text);
  }
};
