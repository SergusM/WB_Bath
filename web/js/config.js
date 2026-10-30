// Настройки интерфейса. Адрес брокера можно переопределить параметром ?mqtt=ws://…
window.BATH_CONFIG = {
  // null — тот же хост, что у страницы, штатный websocket-порт mosquitto на WB
  mqttUrl: null,
  mqttPort: 18883,
  prefix: "/app",
  ackTimeoutMs: 3000,
  // /app/state публикуется не реже раза в 30 с; дольше 70 с без него — контроллер не в сети
  offlineAfterMs: 70000,
};
