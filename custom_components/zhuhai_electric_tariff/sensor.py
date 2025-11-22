from __future__ import annotations
import logging
from datetime import datetime, time, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

def get_season(month: int) -> str:
    if month in [6,7,8,9,10]:
        return "summer"
    return "winter"

PEAK=[(time(10,0),time(12,0)),(time(17,0),time(19,0))]
NORMAL=[(time(8,0),time(10,0)),(time(12,0),time(17,0)),(time(19,0),time(23,59,59))]
LOW=[(time(0,0),time(8,0))]

def in_range(t: time, ranges):
    for s,e in ranges:
        if s<=t<=e:
            return True
    return False

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    conf = entry.data
    sensors = [
        ZhuhaiCurrentPriceSensor(conf),
        ZhuhaiDailyCostSensor(conf),
        ZhuhaiMonthlyCostSensor(conf),
    ]
    async_add_entities(sensors, True)

class ZhuhaiCurrentPriceSensor(SensorEntity):
    _attr_name = "zhuhai_current_price"
    _attr_unique_id = "zhuhai_current_price"
    _attr_native_unit_of_measurement = "分/千瓦时"

    def __init__(self, conf):
        self.conf = conf
        self._state = None

    @property
    def native_value(self):
        now = datetime.now()
        t = time(now.hour, now.minute)
        if in_range(t, PEAK):
            return float(self.conf.get("tou_high", 102.03))
        elif in_range(t, NORMAL):
            return float(self.conf.get("tou_normal", 82.01))
        else:
            return float(self.conf.get("tou_low", 62.81))

    @property
    def extra_state_attributes(self):
        return {"season": get_season(datetime.now().month), "timestamp": datetime.now().isoformat()}

class ZhuhaiDailyCostSensor(SensorEntity):
    _attr_name = "zhuhai_daily_cost"
    _attr_unique_id = "zhuhai_daily_cost"
    _attr_native_unit_of_measurement = "分"

    def __init__(self, conf):
        self.conf = conf
        self._last_reset = datetime.now().date()
        self._accum_cost = 0.0

    async def async_update(self):
        # For a simple demo: increment cost by current_price * assumed usage (kWh)
        now = datetime.now()
        if now.date() != self._last_reset:
            self._last_reset = now.date()
            self._accum_cost = 0.0
        # Assume a small sample usage since we don't read an energy meter here
        usage_kwh = 0.1  # placeholder — in practice read from energy meter entity
        current_price = ZhuhaiCurrentPriceSensor(self.conf).native_value / 100.0  # convert 分->元
        self._accum_cost += usage_kwh * current_price * 100  # keep in 分
        self._state = round(self._accum_cost, 2)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {"last_reset": str(self._last_reset)}

class ZhuhaiMonthlyCostSensor(SensorEntity):
    _attr_name = "zhuhai_monthly_cost"
    _attr_unique_id = "zhuhai_monthly_cost"
    _attr_native_unit_of_measurement = "分"

    def __init__(self, conf):
        self.conf = conf
        self._month = datetime.now().month
        self._accum = 0.0

    async def async_update(self):
        now = datetime.now()
        if now.month != self._month:
            self._month = now.month
            self._accum = 0.0
        # Placeholder usage accumulation. Replace with real meter reads (from Energy)
        usage_kwh = 1.0
        current_price = ZhuhaiCurrentPriceSensor(self.conf).native_value / 100.0
        self._accum += usage_kwh * current_price * 100
        self._state = round(self._accum, 2)

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {"month": self._month}
