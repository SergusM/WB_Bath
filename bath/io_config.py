"""Конфигурация входов и выходов контроллера Wiren Board (баня).

Источник: IO_list.md (разбор flows.json).
Здесь только описание железа и постоянные параметры, логики нет.

MQTT-топики Wiren Board:
    состояние:  /devices/<device>/controls/<control>
    команда:    /devices/<device>/controls/<control>/on
    ошибка:     /devices/<device>/controls/<control>/meta/error
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Базовые типы
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Control:
    """Один контрол устройства Wiren Board."""
    device: str
    control: str
    name: str = ""

    @property
    def topic(self) -> str:
        return f"/devices/{self.device}/controls/{self.control}"

    @property
    def cmd_topic(self) -> str:
        return f"{self.topic}/on"

    @property
    def error_topic(self) -> str:
        return f"{self.topic}/meta/error"


class Relay(Control):
    """Выход (реле). Пишем в cmd_topic, состояние читаем из topic."""


class Input(Control):
    """Дискретный вход (кнопка)."""


@dataclass(frozen=True)
class TempSensor(Control):
    """Датчик температуры wb-mai6. correction прибавляется к показанию."""
    correction: float = 0.0


@dataclass(frozen=True)
class Button:
    """Кнопка и реле, которые показывают её состояние."""
    name: str
    input: Input
    indicators: tuple[Relay, ...] = ()


class Room(Enum):
    SPA = "СПА"
    STEAM = "Парная"


class ZoneKind(Enum):
    """Тип поверхности зоны нагрева, по нему выбирается уставка."""
    FLOOR = "Пол"
    BENCH = "Лежак"
    WALL_LOW = "Стена низ"
    WALL_MID = "Стена середина"
    WALL_TOP = "Стена верх"
    CEILING = "Потолок"
    STOVE = "Печка"       # испаритель и парогенератор


@dataclass(frozen=True)
class RoomSetpoints:
    """Уставки комнаты по типам поверхностей, °C."""
    floor: float
    bench: float
    wall_low: float
    wall_mid: float
    wall_top: float
    ceiling: float
    stove: float

    def get(self, kind: ZoneKind) -> float:
        return {
            ZoneKind.FLOOR: self.floor,
            ZoneKind.BENCH: self.bench,
            ZoneKind.WALL_LOW: self.wall_low,
            ZoneKind.WALL_MID: self.wall_mid,
            ZoneKind.WALL_TOP: self.wall_top,
            ZoneKind.CEILING: self.ceiling,
            ZoneKind.STOVE: self.stove,
        }[kind]


class Preset(Enum):
    """Предустановленные режимы. Значение — топик режима в старом потоке."""
    OFF = "off"
    BEACH_AT_SUNSET = "beach_at_sunset"
    BEACH = "beach"
    IR_SAUNA = "IR_sauna"
    HAMAM = "hamam"
    SPA = "SPA"
    STEAM_BATH = "steam_bath"
    RUSSIAN_BATH = "russian_bath"


PRESET_TITLES = {
    Preset.OFF: "Выкл",
    Preset.BEACH_AT_SUNSET: "Вечерний пляж",
    Preset.BEACH: "Пляж",
    Preset.IR_SAUNA: "ИК-сауна",
    Preset.HAMAM: "Хамам",
    Preset.SPA: "СПА",
    Preset.STEAM_BATH: "Паровая баня",
    Preset.RUSSIAN_BATH: "Русская баня",
}


@dataclass(frozen=True)
class HeatZone:
    """Зона нагрева: реле + датчик + уставка с гистерезисом."""
    index: int            # индекс в heaters[] / tempsensors[] / setpoints[] исходного потока
    name: str
    room: Optional[Room]
    kind: Optional[ZoneKind]           # None — оборудование со своей уставкой
    relay: Relay
    sensor: TempSensor
    max_temp: float                    # аварийное отключение, °C
    hysteresis: float = 1.0


# ---------------------------------------------------------------------------
# Общие параметры
# ---------------------------------------------------------------------------

HEATER_HYSTERESIS = 1.0          # °C, вкл при T < SP-1, выкл при T > SP+1
ZONE_SENSOR_CORRECTION = -5.0    # °C, поправка к датчикам зон 1–20
ZONE_MAX_TEMP = 90               # °C, отсечка зоны нагрева
STEAM_GEN_MAX_TEMP = 470.0       # °C, отсечка испарителя и парогенератора
ZAPARNIK_SETPOINT = 130.0        # °C
ZAPARNIK_MAX_TEMP = 150.0        # °C отсечка запарника
VENT_AUTO_RETURN_S = 15 * 60     # из «Проветривания» назад в «Пропарку»
FACE_FAN_AUTO_OFF_S = 15 * 60    # автоотключение лицевого фена
LONG_PRESS_RGB_S = 1.0           # удержание кнопки RGB -> выкл
LONG_PRESS_MASTER_S = 1.5        # удержание мастер-клавиши -> выключить всё
HEATER_ON_DELAY_S = 0.1          # пауза между командами включения нагревателей (контакторы)
SENSOR_STALE_S = 60              # нет показаний дольше -> датчик считается неисправным
RELAY_RESYNC_S = 10              # период сверки команд реле с фактическим состоянием
WATERFALL_DEFAULT_S = 7         # длительность пролива обливного по умолчанию
WATERFALL_MAX_S = 15
ZONE_MAX_SETPOINT = 85           # предел ручной уставки зоны, °C (ниже ZONE_MAX_TEMP)
STOVE_MAX_SETPOINT = 450         # предел ручной уставки печки, °C (ниже STEAM_GEN_MAX_TEMP)
STATE_PUBLISH_S = 30             # период публикации полного состояния без изменений

# MQTT API для интерфейса: <APP_PREFIX>/cmd, /state, /ack, /event
APP_PREFIX = "/app"

# Стандартные уставки предустановленных режимов (функция Main control в flows.json).
# Режим применяется к СПА и к парной по отдельности. Печка есть только в парной,
# в СПА поле stove не используется.
PRESET_SETPOINTS = {
    Preset.OFF: RoomSetpoints(floor=0, bench=0, wall_low=0, wall_mid=0,
                              wall_top=0, ceiling=0, stove=0),
    Preset.BEACH_AT_SUNSET: RoomSetpoints(floor=36, bench=42, wall_low=42, wall_mid=0,
                                          wall_top=0, ceiling=0, stove=0),
    Preset.BEACH: RoomSetpoints(floor=42, bench=42, wall_low=42, wall_mid=42,
                                wall_top=42, ceiling=42, stove=0),
    Preset.IR_SAUNA: RoomSetpoints(floor=42, bench=42, wall_low=44, wall_mid=52,
                                   wall_top=56, ceiling=60, stove=0),
    Preset.HAMAM: RoomSetpoints(floor=42, bench=42, wall_low=42, wall_mid=0,
                                wall_top=0, ceiling=0, stove=250),
    Preset.SPA: RoomSetpoints(floor=42, bench=42, wall_low=48, wall_mid=52,
                              wall_top=56, ceiling=58, stove=0),
    Preset.STEAM_BATH: RoomSetpoints(floor=42, bench=42, wall_low=44, wall_mid=52,
                                     wall_top=56, ceiling=60, stove=350),
    Preset.RUSSIAN_BATH: RoomSetpoints(floor=42, bench=42, wall_low=54, wall_mid=66,
                                       wall_top=76, ceiling=80, stove=450),
}


# ---------------------------------------------------------------------------
# Датчики температуры (wb-mai6)
# ---------------------------------------------------------------------------

# СПА
T_SPA_BENCH_1 = TempSensor("wb-mai6_106", "IN 1 Temperature", "СПА, лежак 1", ZONE_SENSOR_CORRECTION)
T_SPA_BENCH_2 = TempSensor("wb-mai6_106", "IN 2 Temperature", "СПА, лежак 2", ZONE_SENSOR_CORRECTION)
T_SPA_BENCH_3 = TempSensor("wb-mai6_106", "IN 3 Temperature", "СПА, лежак 3", ZONE_SENSOR_CORRECTION)
T_SPA_BENCH_4 = TempSensor("wb-mai6_106", "IN 4 Temperature", "СПА, лежак 4", ZONE_SENSOR_CORRECTION)
T_SPA_BENCH_5 = TempSensor("wb-mai6_106", "IN 5 Temperature", "СПА, лежак 5", ZONE_SENSOR_CORRECTION)
T_SPA_BENCH_6 = TempSensor("wb-mai6_106", "IN 6 Temperature", "СПА, лежак 6", ZONE_SENSOR_CORRECTION)
T_SPA_FLOOR = TempSensor("wb-mai6_211", "IN 1 Temperature", "СПА, пол", ZONE_SENSOR_CORRECTION)
T_SPA_WALL_LOW = TempSensor("wb-mai6_211", "IN 2 Temperature", "СПА, стена низ", ZONE_SENSOR_CORRECTION)
T_SPA_WALL_MID = TempSensor("wb-mai6_211", "IN 3 Temperature", "СПА, стена середина", ZONE_SENSOR_CORRECTION)
T_SPA_WALL_TOP = TempSensor("wb-mai6_211", "IN 4 Temperature", "СПА, стена верх", ZONE_SENSOR_CORRECTION)
T_SPA_CEILING_1 = TempSensor("wb-mai6_211", "IN 5 Temperature", "СПА, потолок 1 (душ)", ZONE_SENSOR_CORRECTION)
T_SPA_CEILING_2 = TempSensor("wb-mai6_211", "IN 6 Temperature", "СПА, потолок 2", ZONE_SENSOR_CORRECTION)

# Парная
T_STEAM_BENCH_1 = TempSensor("wb-mai6_127", "IN 1 Temperature", "Парная, лежак 1", ZONE_SENSOR_CORRECTION)
T_STEAM_BENCH_2 = TempSensor("wb-mai6_127", "IN 2 Temperature", "Парная, лежак 2", ZONE_SENSOR_CORRECTION)
T_STEAM_BENCH_3 = TempSensor("wb-mai6_127", "IN 3 Temperature", "Парная, лежак 3", ZONE_SENSOR_CORRECTION)
T_STEAM_FLOOR = TempSensor("wb-mai6_127", "IN 4 Temperature", "Парная, пол", ZONE_SENSOR_CORRECTION)
T_STEAM_WALL_LOW = TempSensor("wb-mai6_127", "IN 5 Temperature", "Парная, стена низ", ZONE_SENSOR_CORRECTION)
T_STEAM_WALL_MID = TempSensor("wb-mai6_127", "IN 6 Temperature", "Парная, стена середина", ZONE_SENSOR_CORRECTION)
T_STEAM_WALL_TOP = TempSensor("wb-mai6_39", "IN 1 Temperature", "Парная, стена верх", ZONE_SENSOR_CORRECTION)
T_STEAM_CEILING = TempSensor("wb-mai6_39", "IN 2 Temperature", "Парная, потолок", ZONE_SENSOR_CORRECTION)

# Оборудование (без поправки)
T_TEST_BLOCK = TempSensor("wb-mai6_39", "IN 3 Temperature", "Тестовый блок")
T_ZAPARNIK = TempSensor("wb-mai6_39", "IN 4 Temperature", "Запарник")
T_EVAPORATOR = TempSensor("wb-mai6_39", "IN 5 Temperature", "Испаритель")
T_STEAM_GENERATOR = TempSensor("wb-mai6_39", "IN 6 Temperature", "Парогенератор")


# ---------------------------------------------------------------------------
# Реле нагревателей
# ---------------------------------------------------------------------------

R_SPA_BENCH_1 = Relay("wb-gpio", "EXT2_K4", "Нагрев: СПА, лежак 1")
R_SPA_BENCH_2 = Relay("wb-gpio", "EXT2_K5", "Нагрев: СПА, лежак 2")
R_SPA_BENCH_3 = Relay("wb-gpio", "EXT2_K6", "Нагрев: СПА, лежак 3")
R_SPA_BENCH_4 = Relay("wb-gpio", "EXT2_K7", "Нагрев: СПА, лежак 4")
R_SPA_BENCH_5 = Relay("wb-gpio", "EXT2_K8", "Нагрев: СПА, лежак 5")
R_SPA_BENCH_6 = Relay("wb-gpio", "EXT3_K1", "Нагрев: СПА, лежак 6")
R_SPA_FLOOR = Relay("wb-gpio", "EXT3_K2", "Нагрев: СПА, пол")
R_SPA_WALL_LOW = Relay("wb-gpio", "EXT3_K3", "Нагрев: СПА, стена низ")
R_SPA_WALL_MID = Relay("wb-gpio", "EXT3_K4", "Нагрев: СПА, стена середина")
R_SPA_WALL_TOP = Relay("wb-gpio", "EXT3_K5", "Нагрев: СПА, стена верх")
R_SPA_CEILING_1 = Relay("wb-gpio", "EXT3_K6", "Нагрев: СПА, потолок 1 (душ)")
R_SPA_CEILING_2 = Relay("wb-gpio", "EXT3_K7", "Нагрев: СПА, потолок 2")

R_STEAM_BENCH_1 = Relay("wb-gpio", "EXT3_K8", "Нагрев: парная, лежак 1")
R_STEAM_BENCH_2 = Relay("wb-gpio", "EXT4_K1", "Нагрев: парная, лежак 2")
R_STEAM_BENCH_3 = Relay("wb-gpio", "EXT4_K2", "Нагрев: парная, лежак 3")
R_STEAM_FLOOR = Relay("wb-gpio", "EXT4_K7", "Нагрев: парная, пол")
R_STEAM_WALL_LOW = Relay("wb-gpio", "EXT4_K6", "Нагрев: парная, стена низ")
R_STEAM_WALL_MID = Relay("wb-gpio", "EXT4_K5", "Нагрев: парная, стена середина")
R_STEAM_WALL_TOP = Relay("wb-gpio", "EXT4_K4", "Нагрев: парная, стена верх")
R_STEAM_CEILING = Relay("wb-gpio", "EXT4_K3", "Нагрев: парная, потолок")

R_ZAPARNIK_HEAT = Relay("wb-gpio", "EXT2_K2", "Запарник, нагрев")
R_EVAPORATOR = Relay("wb-mr6c_151", "K5", "Испаритель")
R_STEAM_GENERATOR = Relay("wb-mr6c_151", "K4", "Парогенератор")


# ---------------------------------------------------------------------------
# Зоны нагрева
# ---------------------------------------------------------------------------

SPA_ZONES = [
    HeatZone(0, "Лежак 1", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_1, T_SPA_BENCH_1, ZONE_MAX_TEMP),
    HeatZone(1, "Лежак 2", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_2, T_SPA_BENCH_2, ZONE_MAX_TEMP),
    HeatZone(2, "Лежак 3", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_3, T_SPA_BENCH_3, ZONE_MAX_TEMP),
    HeatZone(3, "Лежак 4", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_4, T_SPA_BENCH_4, ZONE_MAX_TEMP),
    HeatZone(4, "Лежак 5", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_5, T_SPA_BENCH_5, ZONE_MAX_TEMP),
    HeatZone(5, "Лежак 6", Room.SPA, ZoneKind.BENCH, R_SPA_BENCH_6, T_SPA_BENCH_6, ZONE_MAX_TEMP),
    HeatZone(6, "Пол", Room.SPA, ZoneKind.FLOOR, R_SPA_FLOOR, T_SPA_FLOOR, ZONE_MAX_TEMP),
    HeatZone(7, "Стена низ", Room.SPA, ZoneKind.WALL_LOW, R_SPA_WALL_LOW, T_SPA_WALL_LOW, ZONE_MAX_TEMP),
    HeatZone(8, "Стена середина", Room.SPA, ZoneKind.WALL_MID, R_SPA_WALL_MID, T_SPA_WALL_MID, ZONE_MAX_TEMP),
    HeatZone(9, "Стена верх", Room.SPA, ZoneKind.WALL_TOP, R_SPA_WALL_TOP, T_SPA_WALL_TOP, ZONE_MAX_TEMP),
    HeatZone(10, "Потолок 1 (душ)", Room.SPA, ZoneKind.CEILING, R_SPA_CEILING_1, T_SPA_CEILING_1, ZONE_MAX_TEMP),
    HeatZone(11, "Потолок 2", Room.SPA, ZoneKind.CEILING, R_SPA_CEILING_2, T_SPA_CEILING_2, ZONE_MAX_TEMP),
]

STEAM_ZONES = [
    HeatZone(12, "Лежак 1", Room.STEAM, ZoneKind.BENCH, R_STEAM_BENCH_1, T_STEAM_BENCH_1, ZONE_MAX_TEMP),
    HeatZone(13, "Лежак 2", Room.STEAM, ZoneKind.BENCH, R_STEAM_BENCH_2, T_STEAM_BENCH_2, ZONE_MAX_TEMP),
    HeatZone(14, "Лежак 3", Room.STEAM, ZoneKind.BENCH, R_STEAM_BENCH_3, T_STEAM_BENCH_3, ZONE_MAX_TEMP),
    HeatZone(15, "Пол", Room.STEAM, ZoneKind.FLOOR, R_STEAM_FLOOR, T_STEAM_FLOOR, ZONE_MAX_TEMP),
    HeatZone(16, "Стена низ", Room.STEAM, ZoneKind.WALL_LOW, R_STEAM_WALL_LOW, T_STEAM_WALL_LOW, ZONE_MAX_TEMP),
    HeatZone(17, "Стена середина", Room.STEAM, ZoneKind.WALL_MID, R_STEAM_WALL_MID, T_STEAM_WALL_MID, ZONE_MAX_TEMP),
    HeatZone(18, "Стена верх", Room.STEAM, ZoneKind.WALL_TOP, R_STEAM_WALL_TOP, T_STEAM_WALL_TOP, ZONE_MAX_TEMP),
    HeatZone(19, "Потолок", Room.STEAM, ZoneKind.CEILING, R_STEAM_CEILING, T_STEAM_CEILING, ZONE_MAX_TEMP),
]

# В исходном потоке реле запарника считалось по датчику тестового блока
# (сдвиг индексов, см. IO_list.md п. 3.1). Здесь взят правильный датчик IN 4.
ZONE_ZAPARNIK = HeatZone(20, "Запарник", None, None, R_ZAPARNIK_HEAT, T_ZAPARNIK,
                         ZAPARNIK_MAX_TEMP)
ZONE_EVAPORATOR = HeatZone(22, "Испаритель", Room.STEAM, ZoneKind.STOVE, R_EVAPORATOR, T_EVAPORATOR,
                           STEAM_GEN_MAX_TEMP)
ZONE_STEAM_GENERATOR = HeatZone(23, "Парогенератор", Room.STEAM, ZoneKind.STOVE, R_STEAM_GENERATOR,
                                T_STEAM_GENERATOR, STEAM_GEN_MAX_TEMP)

ALL_ZONES = [*SPA_ZONES, *STEAM_ZONES,
             ZONE_ZAPARNIK, ZONE_EVAPORATOR, ZONE_STEAM_GENERATOR]
ZONES_BY_INDEX = {z.index: z for z in ALL_ZONES}

# Потолки СПА работают только парой
SPA_CEILING_PAIR = (SPA_ZONES[10], SPA_ZONES[11])
# Испаритель и парогенератор выключаются оба, если любой датчик > max_temp
STEAM_GEN_GROUP = (ZONE_EVAPORATOR, ZONE_STEAM_GENERATOR)


# ---------------------------------------------------------------------------
# Вентиляция
# ---------------------------------------------------------------------------

class VentMode(IntEnum):
    STEAMING = 0       # X0 «Пропарка»
    STEAM_SHOWER = 1   # X1 «Паровой душ» (ступени 1–4)
    NATURAL = 2        # X2 «Естественная тяга»
    AIRING = 3         # X3 «Проветривание»


STEAM_SHOWER_STAGES = 4

# Кнопки режимов с реле индикации (взаимоисключающие). Парная повторяет СПА.
VENT_BUTTONS = {
    Room.SPA: {
        VentMode.STEAMING: Button(
            "СПА: пропарка",
            Input("wb-gpio", "EXT1_IN1"),
            (Relay("wb-gpio", "EXT4_K8", "СПА: пропарка"),)),
        VentMode.STEAM_SHOWER: Button(
            "СПА: паровой душ",
            Input("wb-gpio", "EXT1_IN2"),
            (Relay("wb-gpio", "EXT2_K16", "СПА: паровой душ"),)),
        VentMode.NATURAL: Button(
            "СПА: естественная тяга",
            Input("wb-gpio", "EXT1_IN3"),
            (Relay("wb-gpio", "EXT2_K15", "СПА: естественная тяга"),)),
        VentMode.AIRING: Button(
            "СПА: проветривание",
            Input("wb-gpio", "EXT1_IN4"),
            (Relay("wb-gpio", "EXT2_K14", "СПА: проветривание"),)),
    },
    Room.STEAM: {
        VentMode.STEAMING: Button(
            "Парная: пропарка",
            Input("wb-gpio", "EXT1_IN5"),
            (Relay("wb-gpio", "EXT2_K13", "Парная: пропарка"),)),
        VentMode.STEAM_SHOWER: Button(
            "Парная: паровой душ",
            Input("wb-gpio", "EXT1_IN6"),
            (Relay("wb-gpio", "EXT2_K12", "Парная: паровой душ"),)),
        VentMode.NATURAL: Button(
            "Парная: естественная тяга",
            Input("wb-gpio", "EXT1_IN7"),
            (Relay("wb-gpio", "EXT2_K11", "Парная: естественная тяга"),)),
        VentMode.AIRING: Button(
            "Парная: проветривание",
            Input("wb-gpio", "EXT1_IN8"),
            (Relay("wb-gpio", "EXT2_K9", "Парная: проветривание"),)),
    },
}

# Исполнительные реле вентиляции (vent[0..5]); назначение выведено из режимов
VENT = [
    Relay("wb-gpio", "EXT4_K15", "Вентиляция 0"),
    Relay("wb-gpio", "EXT4_K14", "Вентиляция 1"),
    Relay("wb-gpio", "EXT4_K13", "Вентиляция 2"),
    Relay("wb-gpio", "EXT4_K12", "Вентиляция 3"),
    Relay("wb-gpio", "EXT4_K11", "Вентиляция 4"),
    Relay("wb-gpio", "EXT4_K10", "Вентиляция 5"),
]

# Какие vent[] включены в каждом режиме / ступени (индексы VENT)
VENT_PATTERNS = {
    (VentMode.STEAMING, 0): (),
    (VentMode.STEAM_SHOWER, 1): (0, 4),
    (VentMode.STEAM_SHOWER, 2): (1, 4),
    (VentMode.STEAM_SHOWER, 3): (2, 4),
    (VentMode.STEAM_SHOWER, 4): (3, 4),
    (VentMode.NATURAL, 0): (4, 5),
    (VentMode.AIRING, 0): (3, 5),
}


# ---------------------------------------------------------------------------
# Освещение
# ---------------------------------------------------------------------------

R_LIGHT_STEAM = Relay("wb-gpio", "EXT3_K12", "Бра парной")
R_LIGHT_SPA = Relay("wb-gpio", "EXT3_K13", "Бра СПА")

RGB_SPA = (
    Relay("wb-mr6c_223", "K1", "RGB СПА R"),
    Relay("wb-mr6c_223", "K2", "RGB СПА G"),
    Relay("wb-mr6c_223", "K3", "RGB СПА B"),
)
RGB_STEAM = (
    Relay("wb-mr6c_223", "K4", "RGB парной R"),
    Relay("wb-mr6c_223", "K5", "RGB парной G"),
    Relay("wb-mr6c_223", "K6", "RGB парной B"),
)

# Режимы RGB 0–7: (R, G, B)
RGB_MODES = [
    (0, 0, 0),  # выкл
    (1, 1, 1),  # белый
    (1, 0, 0),  # R
    (0, 1, 0),  # G
    (0, 0, 1),  # B
    (1, 1, 0),  # R+G
    (0, 1, 1),  # G+B
    (1, 0, 1),  # R+B
]

# Режимы бра по кругу: (бра СПА, бра парной)
LIGHT_MODES = [
    (0, 0),  # выкл
    (1, 1),  # оба
    (1, 0),  # только СПА
    (0, 1),  # только парная
]

LIGHT_RELAYS = [R_LIGHT_STEAM, R_LIGHT_SPA, *RGB_SPA, *RGB_STEAM]


# ---------------------------------------------------------------------------
# Прочие выходы
# ---------------------------------------------------------------------------

R_ZAPARNIK_ENABLE = Relay("wb-gpio", "EXT3_K15", "Запарник, включение режима")
R_FACE_FAN = Relay("wb-gpio", "EXT3_K16", "Лицевой фен")
R_FACE_FAN_DUP = Relay("wb-gpio", "EXT2_K10", "Лицевой фен, дублирующий выход")
R_WATERFALL = Relay("wb-gpio", "EXT3_K11", "Обливное устройство")
R_ALWAYS_ON = Relay("wb-gpio", "EXT2_K1", "Всегда включено")


# ---------------------------------------------------------------------------
# Прочие кнопки
# ---------------------------------------------------------------------------

BTN_LIGHT_STEAM = Button("Бра парной", Input("wb-gpio", "EXT1_IN9"),
                          (R_LIGHT_STEAM,))
BTN_LIGHT_SPA = Button("Бра (переключение режимов)", Input("wb-gpio", "EXT1_IN10"),
                        (R_LIGHT_SPA, R_LIGHT_STEAM))
BTN_RGB_STEAM = Button("RGB парной", Input("wb-gpio", "EXT1_IN11"), RGB_STEAM)
BTN_RGB_SPA = Button("RGB СПА", Input("wb-gpio", "EXT1_IN12"), RGB_SPA)
BTN_MASTER = Button("Мастер-клавиша", Input("wb-gpio", "EXT1_IN13"))
BTN_ZAPARNIK = Button("Запарник", Input("wb-gpio", "EXT1_IN14"),
                      (R_ZAPARNIK_ENABLE,))
BTN_FACE_FAN = Button("Лицевой фен", Input("wb-mr6c_223", "Input 5"),
                      (R_FACE_FAN, R_FACE_FAN_DUP))
BTN_WATERFALL = Button("Обливное устройство", Input("wb-mr6c_223", "Input 6"),
                       (R_WATERFALL,))


# ---------------------------------------------------------------------------
# Счётчик электроэнергии (только мониторинг)
# ---------------------------------------------------------------------------

ENERGY_METER_DEVICE = "wb-map3e_220"
ENERGY_METER = [
    Control(ENERGY_METER_DEVICE, c, c) for c in (
        "Total AP energy", "AP energy L1", "AP energy L2", "AP energy L3",
        "Urms L1", "Urms L2", "Urms L3",
        "Irms L1", "Irms L2", "Irms L3",
        "Total P", "P L1", "P L2", "P L3",
    )
]


# ---------------------------------------------------------------------------
# Сводные списки
# ---------------------------------------------------------------------------

ALL_TEMP_SENSORS = [z.sensor for z in ALL_ZONES] + [T_TEST_BLOCK]

ALL_BUTTONS = (
    [b for room in VENT_BUTTONS.values() for b in room.values()]
    + [BTN_LIGHT_STEAM, BTN_LIGHT_SPA, BTN_RGB_STEAM, BTN_RGB_SPA,
       BTN_MASTER, BTN_ZAPARNIK, BTN_FACE_FAN, BTN_WATERFALL]
)

ALL_INPUTS = [b.input for b in ALL_BUTTONS]

ALL_RELAYS = list(dict.fromkeys(
    [z.relay for z in ALL_ZONES]
    + [r for b in ALL_BUTTONS for r in b.indicators]
    + VENT
    + LIGHT_RELAYS
    + [R_ALWAYS_ON]
))


if __name__ == "__main__":
    # Самопроверка: нет дублей и всё печатается
    for title, items in (("Реле", ALL_RELAYS), ("Входы", ALL_INPUTS),
                         ("Датчики", ALL_TEMP_SENSORS)):
        topics = [i.topic for i in items]
        dups = {t for t in topics if topics.count(t) > 1}
        assert not dups, f"{title}: дубли {dups}"
        print(f"\n== {title} ({len(items)}) ==")
        for i in items:
            print(f"  {i.topic:<55} {i.name}")

    print("\n== Кнопки ==")
    for b in ALL_BUTTONS:
        ind = ", ".join(r.control for r in b.indicators) or "—"
        print(f"  {b.input.control:<10} {b.name:<28} -> {ind}")

    print("\n== Уставки режимов ==")
    print(f"  {'':<14}" + "".join(f"{k.value[:9]:>10}" for k in ZoneKind))
    for preset, sp in PRESET_SETPOINTS.items():
        print(f"  {PRESET_TITLES[preset]:<14}"
              + "".join(f"{sp.get(k):>10}" for k in ZoneKind))
