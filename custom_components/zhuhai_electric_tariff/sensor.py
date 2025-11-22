# sensor.py - 珠海电费模板传感器 (整合了所有常量和逻辑)

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENERGY_KILO_WATT_HOUR, CURRENCY_RENMINBI, CONF_NAME
from datetime import datetime, date
import logging
import math

_LOGGER = logging.getLogger(__name__)

# ----------------- I. 常量部分 -----------------

DOMAIN = "zhuhai_electric_tariff"
CONF_ENERGY_SENSOR_ID = "energy_sensor_id"

UNIT_OF_MEASUREMENT = f"{CURRENCY_RENMINBI}/{ENERGY_KILO_WATT_HOUR}"
SENSOR_NAME = "Zhuhai Electricity Tariff Price"
ICON = "mdi:currency-usd"

# 固定成本 (Fixed Costs: 可再生能源电价附加 + 水利基金/附加) - 单位：元/kWh
# 0.019875 (再生) + 0.67 (附加) = 0.689875
FIXED_COSTS = 0.689875 

# 珠海阶梯分时价格表 (电度电价, 单位: 元/kWh) - 非一户一表
ZH_TARIFF_RATES = {
    # 峰谷电价（基础电度电价）
    "peak_time_rates": {
        "summer": {  # 夏季标准 (6-10月)
            "尖峰": 1.0203,
            "平": 0.6002,
            "谷": 0.2281,
        },
        "non_summer": {  # 非夏季标准 (11-次年5月)
            "高峰": 0.6002,
            "低谷": 0.2281,
        }
    },
    # 阶梯电价加价 (Tier Adder)
    "tier_adders": {
        "tier_2": 0.05,  # 阶梯2加价
        "tier_3": 0.30,  # 阶梯3加价
    },
    # 阶梯电量阈值 (Tier Thresholds)
    "tier_thresholds": {
        "summer": (400, 600),   # 梯级1: 0-400; 梯级2: 401-600; 梯级3: > 600
        "non_summer": (260, 400), # 梯级1: 0-260; 梯级2: 261-400; 梯级3: > 400
    }
}

# 时间段定义 (基于备注说明) - 使用 24 小时制 (小时 H: 0-23)
TIME_PERIODS = {
    # 尖峰: 10:00-12:00, 14:00-17:00 (夏季专有)
    "peak_jianfeng": [(10, 12), (14, 17)],
    # 谷段: 00:00-08:00, 19:00-24:00 (全年适用)
    "valley_gu": [(0, 8), (19, 24)],
}

# ----------------- II. 传感器设置 -----------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """从配置条目设置传感器."""
    total_energy_sensor_id = entry.data[CONF_ENERGY_SENSOR_ID]
    
    async_add_entities([
        ZhuhaiTariffSensor(hass, entry.data[CONF_NAME], total_energy_sensor_id)
    ], True)

class ZhuhaiTariffSensor(SensorEntity):
    """珠海电费模板传感器，包含自维护的月度用量追踪."""

    def __init__(self, hass, name, total_energy_sensor_id):
        self.hass = hass
        self._name = name
        self._total_energy_sensor_id = total_energy_sensor_id
        self._state = None
        self._unit_of_measurement = UNIT_OF_MEASUREMENT
        self._attr_unique_id = f"{DOMAIN}_{total_energy_sensor_id}"
        
        # 存储本月用量的起点（总电量读数）和上次重置日期
        self._monthly_reset_point = None
        self._last_reset_date = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def icon(self):
        return ICON

    @property
    def extra_state_attributes(self):
        """添加额外属性，用于显示月度用量和重置点."""
        current_usage = self._calculate_monthly_usage()
        return {
            "current_monthly_usage_kwh": round(current_usage, 3) if current_usage is not None else "Unknown",
            "reset_point_kwh": self._monthly_reset_point,
            "last_reset_date": self._last_reset_date.isoformat() if self._last_reset_date else "Never",
        }

    def _calculate_monthly_usage(self):
        """计算本月的累计用量."""
        total_energy_state = self.hass.states.get(self._total_energy_sensor_id)
        if total_energy_state and self._monthly_reset_point is not None:
            try:
                current_total = float(total_energy_state.state)
                # 检查是否发生总表回滚（比如抄表员重置或传感器错误）
                if current_total < self._monthly_reset_point:
                    _LOGGER.warning("总电量读数发生回滚，无法计算月度用量。")
                    return 0.0
                return current_total - self._monthly_reset_point
            except ValueError:
                _LOGGER.warning("总电量传感器状态无效，无法计算月度用量。")
                return None
        return 0.0

    async def async_update(self):
        """根据时间、季节和用量计算当前价格，并处理月度重置."""
        now = datetime.now()
        today = now.date()
        
        # 1. 检查是否需要月度重置 (每月1号，且上次重置月份不是当月)
        if self._last_reset_date is None or (today.day == 1 and self._last_reset_date.month != today.month):
            total_energy_state = self.hass.states.get(self._total_energy_sensor_id)
            
            if total_energy_state and total_energy_state.state.lower() not in ('unknown', 'unavailable'):
                try:
                    self._monthly_reset_point = float(total_energy_state.state)
                    self._last_reset_date = today
                    _LOGGER.info(f"珠海电价：已在 {today} 重置月度起点为 {self._monthly_reset_point} kWh。")
                except ValueError:
                    _LOGGER.error("无法读取总电量传感器状态以设置重置点。")
                    self._state = None
                    return 

        # 2. 获取月度用量
        monthly_usage = self._calculate_monthly_usage()
        if monthly_usage is None:
            self._state = None
            return
            
        # 3. 确定基础电度电价 (Base Price) - 峰谷平
        month = now.month
        hour = now.hour
        is_summer = month >= 6 and month <= 10
        base_rate = 0.0
        
        if is_summer:
            # 尖峰优先
            if any(start <= hour < end for start, end in TIME_PERIODS["peak_jianfeng"]):
                base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["尖峰"]
            # 谷段次之
            elif any(start <= hour < end for start, end in TIME_PERIODS["valley_gu"]):
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["谷"]
            # 平段 (所有剩余时间)
            else:
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["平"]
        else: # 非夏季
             # 低谷优先
            if any(start <= hour < end for start, end in TIME_PERIODS["valley_gu"]):
                base_rate = ZH_TARIFF_RATES["peak_time_rates"]["non_summer"]["低谷"]
            # 高峰 (所有剩余时间)
            else:
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["non_summer"]["高峰"]

        # 4. 确定阶梯加价 (Tier Adder)
        tier_adder = 0.0
        rates_key = "summer" if is_summer else "non_summer"
        threshold_2, threshold_3 = ZH_TARIFF_RATES["tier_thresholds"][rates_key]
        
        if monthly_usage > threshold_3:
            tier_adder = ZH_TARIFF_RATES["tier_adders"]["tier_3"]
        elif monthly_usage > threshold_2:
            tier_adder = ZH_TARIFF_RATES["tier_adders"]["tier_2"]

        # 5. 计算最终价格
        final_price = base_rate + FIXED_COSTS + tier_adder
        
        self._state = round(final_price, 4)
        
    async def async_added_to_hass(self):
        """注册状态改变监听器，当总电量改变时更新价格"""
        
        @callback
        def async_state_change(event):
            """处理总电量传感器状态改变事件."""
            self.async_schedule_update_ha_state(True)
        
        async_track_state_change_event(
            self.hass, [self._total_energy_sensor_id], async_state_change
        )
        
        # 初始更新
        await self.async_update()
