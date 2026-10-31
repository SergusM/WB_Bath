# Контроллер бани на Wiren Board

Логика написана на Python и заменяет поток Node-RED (`flows.json`). Связь с контроллером идёт через [python2wb](https://pypi.org/project/python2wb/). Железо описано в `bath/io_config.py`, разбор старого потока лежит в `IO_list.md` и `UI_vs_flows.md`.

## Модули `bath/`

| Файл | Что делает |
|---|---|
| `gateway.py` | Связь с MQTT, кэш команд реле, очередь включения нагревателей (0.1 с между командами), сверка с обратной связью |
| `heating.py` | Режимы комнат, ручные уставки, гистерезис, защиты |
| `ventilation.py` | Вентиляция (пропарка, паровой душ 1–4, тяга, проветривание) и лицевой фен |
| `lighting.py` | Бра, RGB, мастер-клавиша |
| `extras.py` | Обливное с расписанием, запарник |
| `inputs.py` | Нажатия кнопок: короткое и длинное |
| `sensors.py` | Показания датчиков, ошибки, устаревание |
| `alarms.py` | Журнал аварий |
| `storage.py` | `config/settings.json`: ручные уставки и настройки обливного |
| `api.py` | MQTT API для интерфейса |
| `controller.py` | Сборка подсистем и главный цикл |

При старте всё выключено: нагрев, свет, фен, запарник, обливное. Вентиляция стоит в «Пропарке». Выбранные режимы после перезапуска не восстанавливаются. При остановке сервиса нагреватели выключаются.

## Запуск и тесты

```bash
pip install -r requirements.txt
python3 -m bath.main --host <адрес WB> -v
python -m pytest
```

Для тестов брокер не нужен, они идут на `FakeGateway`.

## Установка на контроллер

```bash
scp -r bath requirements.txt deploy root@<wb>:/mnt/data/wb_bath/
ssh root@<wb> "cd /mnt/data/wb_bath && pip3 install -r requirements.txt && cp deploy/wb-bath.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now wb-bath"
```

Прошивку WB обновляйте через `apt`. При обновлении через веб-интерфейс или флешку файл сервиса может пропасть (это предупреждение есть у python2wb).

## Веб-интерфейс

Папка `html/`: статические HTML, CSS и JS без сборки. Браузер сам подключается к mosquitto на WB по MQTT over WebSocket: читает `/app/state` и `/app/info`, команды шлёт в `/app/cmd`. Отдельного веб-сервера у сервиса нет.

Разделы:
- **Нагрев** — СПА и парная рядом, режим выбирается из списка. В ручном режиме уставки меняются кнопками −/+.
- **Климат** — вентиляция со ступенями парового душа, лицевой фен, запарник.
- **Свет** — бра, RGB, мастер-клавиша.
- **Обливное** — пролив, длительность, расписание.
- **Журнал** — аварии и счётчик электроэнергии.

На планшете навигация слева, на телефоне (уже 768 px) — внизу. Оформление в духе старой панели: тёмная тема, объёмные иконки разделов, металлические кнопки вентиляции со светящимся кольцом, фото текущего режима за карточкой комнаты. Картинки взяты из старого интерфейса `html_old/img/` и уменьшены (`html/img/`, около 1,1 МБ).

Адрес брокера по умолчанию — `ws://<хост страницы>:18883/mqtt`, штатный websocket-порт mosquitto на WB. Поменять его можно в `html/js/config.js` или параметром `?mqtt=ws://…`.

Установка: скопировать `html/` на контроллер и открыть `http://<wb>/bath/`.

```bash
scp -r html root@<wb>:/var/www/bath
```

Проверьте на месте, что nginx WB отдаёт `/bath/` и что обновление прошивки не затирает `/var/www/bath`. Если затирает, положите файлы в `/mnt/data/wb_bath/html` и добавьте в конфигурацию nginx `location /bath/ { alias /mnt/data/wb_bath/html/; }`.

При каждом изменении файлов в `html/` увеличивайте номер `?v=N` у подключений CSS и JS в `html/index.html`. Иначе планшеты будут показывать старую версию из кэша.

Демо-режим без брокера и контроллера — `index.html?demo`. Данные берутся из `html/demo/*.json`, их строит настоящий контроллер на `FakeGateway`:

```bash
python tools/gen_web_demo.py
python -m http.server 8090 --directory html
```

Затем откройте `http://localhost:8090/?demo`. Демо только изображает реакцию контроллера на команды и не повторяет его логику.

## MQTT API

| Топик | Направление | Содержимое |
|---|---|---|
| `/app/cmd` | → контроллер | `{"cmd": "...", ...аргументы, "id": "необязательно"}` |
| `/app/ack` | ← | `{"id", "cmd", "ok", "error"?}` |
| `/app/state` | ← retained | полное состояние: при изменениях (не чаще 0.3 с) и раз в 30 с |
| `/app/info` | ← retained | справочник: режимы, типы зон, пределы, список команд |
| `/app/event` | ← | аварии, их снятие, пролив по расписанию |
| `/app/online` | ← retained | `1` — работает, `0` — остановлен штатно |

`room`: `spa` или `steam`.

| cmd | Аргументы |
|---|---|
| `set_preset` | `room`, `preset`: `off`, `hamam`, `steam_bath`, `russian_bath`, `beach_at_sunset`, `beach`, `SPA`, `IR_sauna` |
| `set_manual` | `room` |
| `set_manual_setpoint` | `room`, `kind` (`FLOOR`, `BENCH`, `WALL_LOW`, `WALL_MID`, `WALL_TOP`, `CEILING`, `STOVE`), `value` |
| `room_off` | `room` |
| `vent_press` | `mode`: `STEAMING`, `STEAM_SHOWER`, `NATURAL`, `AIRING` (как физическая кнопка) |
| `vent_set` | `mode`, `stage` (1–4 для `STEAM_SHOWER`) |
| `face_fan`, `zaparnik` | `on` (без него — переключить) |
| `light_next` / `set_light` | — / `spa`, `steam` |
| `rgb_next` / `set_rgb` / `rgb_off` | `room` / `room`, `mode` 0–7 / `room` |
| `master`, `all_light_off` | — |
| `waterfall_pour` | `duration` (с, необязательно) |
| `waterfall_stop` | — |
| `waterfall_set_duration` | `duration` |
| `waterfall_set_schedule` | `enabled`, `times` (`["HH:MM"]`), `days` (`["mon", …]`) |
| `offoff` | — (всё, кроме вентиляции) |
| `alarms_ack`, `get_state` | — |

Пример:

```bash
mosquitto_pub -t /app/cmd -m '{"cmd":"set_preset","room":"steam","preset":"russian_bath"}'
```
