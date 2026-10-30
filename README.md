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
| `set_preset` | `room`, `preset`: `off`, `beach_at_sunset`, `beach`, `IR_sauna`, `hamam`, `SPA`, `steam_bath`, `russian_bath` |
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
