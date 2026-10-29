"""Запуск: python3 -m bath.main --host localhost"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time

from .controller import BathController
from .gateway import WbGateway
from .storage import SettingsStore

DEFAULT_SETTINGS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Контроллер бани на Wiren Board")
    parser.add_argument("--host", default="localhost", help="MQTT-брокер")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--settings", default=DEFAULT_SETTINGS, help="JSON с настройками")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    store = SettingsStore(args.settings)
    gw = WbGateway(args.host, args.port, args.username, args.password)
    ctl = BathController(gw, store)
    try:
        ctl.run(stop)
    finally:
        ctl.shutdown()
        time.sleep(0.5)   # дать paho отправить команды выключения до отключения
        gw.close()


if __name__ == "__main__":
    main()
