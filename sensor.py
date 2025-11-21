# sensor.py 核心逻辑代码

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ENERGY_KILO_WATT_HOUR, CURRENCY_RENMINBI
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from datetime import datetime
import logging

_LOGGER = logging.getLogger(__name__)

# 固定成本 (Fixed Costs: 可再生能源电价附加 + 大水库/水利基金 + 居民生活用电附加)
FIXED_COSTS = 0.019875 + 0.67  # 0.689875 元/kWh

# 珠海阶梯分时价格表 (电度电价, 单位: 元/kWh) - 非一户一表价格
# 价格来自表格中 “电度电价” 列
# 夏季标准 (6-10月) 和 非夏季标准 (11-次年5月)
ZH_TARIFF_RATES = {
    # 峰谷电价（非阶梯电价中的电度电价部分，用于计算基础价格）
    "peak_time_rates": {
        "summer": {
            "尖峰": 1.0203,
            "平": 0.6002,
            "谷": 0.2281,
        },
        "non_summer": {
            # 非夏季标准没有尖峰，用高峰/平/谷价格
            "高峰": 0.6002,
            "平": 0.6002,
            "低谷": 0.2281,
        }
    },
    # 阶梯电价加价 (Tier Adder)
    "tier_adders": {
        "summer": {
            "tier_2": 0.05,  # 401-600 kWh
            "tier_3": 0.30,  # > 600 kWh
        },
        "non_summer": {
            "tier_2": 0.05,  # 261-400 kWh
            "tier_3": 0.30,  # > 400 kWh
        }
    },
    # 阶梯电量阈值 (Tier Thresholds)
    "tier_thresholds": {
        "summer": (400, 600),
        "non_summer": (260, 400),
    }
}

# 时间段定义 (基于备注说明)
TIME_PERIODS = {
    # 尖峰: 10:00-12:00, 14:00-17:00
    "peak_jianfeng": [(10, 12), (14, 17)],
    # 平段: 08:00-10:00, 12:00-14:00, 17:00-19:00, (24:00-次日08:00)
    "flat_ping": [(8, 10), (12, 14), (17, 19), (0, 8)],
    # 谷段: 00:00-08:00, 19:00-24:00 (注: 与平段0-8重叠，按谷段价格为低价执行)
    "valley_gu": [(0, 8), (19, 24)],
}

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """设置平台（此集成不需要配置，直接添加传感器）"""
    async_add_entities([ZhuhaiTariffSensor(hass)], True)

class ZhuhaiTariffSensor(SensorEntity):
    """珠海电费模板传感器"""

    def __init__(self, hass):
        self.hass = hass
        self._state = None
        self._name = "Zhuhai Electricity Tariff Price"
        self._unit_of_measurement = f"{CURRENCY_RENMINBI}/{ENERGY_KILO_WATT_HOUR}"
        # 必须指定一个 Utility Meter 实体来追踪月用量
        self.usage_sensor_entity_id = "sensor.monthly_kwh_usage" 
        
    @property
    def name(self):
        """返回传感器名称."""
        return self._name

    @property
    def state(self):
        """返回当前电价."""
        return self._state

    @property
    def unit_of_measurement(self):
        """返回单位."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """返回图标."""
        return "mdi:currency-usd"

    async def async_added_to_hass(self):
        """注册状态改变监听器，当月度用量或时间改变时更新价格"""

        @callback
        def async_state_change(event):
            """处理用量传感器状态改变事件."""
            self.async_schedule_update_ha_state(True)

        # 监听月度用量传感器的状态变化
        async_track_state_change_event(
            self.hass, [self.usage_sensor_entity_id], async_state_change
        )
        # 初始更新
        await self.async_update()

    async def async_update(self):
        """根据时间、季节和用量计算当前价格."""
        now = datetime.now()
        month = now.month
        hour = now.hour
        
        # 1. 判断季节和价格字典
        is_summer = month >= 6 and month <= 10
        rates_key = "summer" if is_summer else "non_summer"
        
        # 2. 获取月度用量
        usage_state = self.hass.states.get(self.usage_sensor_entity_id)
        try:
            monthly_usage = float(usage_state.state) if usage_state and usage_state.state.lower() not in ('unknown', 'unavailable') else 0.0
        except ValueError:
            monthly_usage = 0.0

        # 3. 确定基础电度电价 (Base Price) - 峰谷平
        base_rate = 0.0
        
        if is_summer:
            # 尖峰
            if any(start <= hour < end for start, end in TIME_PERIODS["peak_jianfeng"]):
                base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["尖峰"]
            # 谷段
            elif any(start <= hour < end for start, end in TIME_PERIODS["valley_gu"]):
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["谷"]
            # 平段 (包含所有剩余时间)
            else:
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["summer"]["平"]
        else: # 非夏季
             # 谷段 (00:00-08:00, 19:00-24:00)
            if any(start <= hour < end for start, end in TIME_PERIODS["valley_gu"]):
                base_rate = ZH_TARIFF_RATES["peak_time_rates"]["non_summer"]["低谷"]
            # 峰段 (所有剩余时间)
            else:
                 base_rate = ZH_TARIFF_RATES["peak_time_rates"]["non_summer"]["高峰"]

        # 4. 确定阶梯加价 (Tier Adder)
        tier_adder = 0.0
        threshold_2, threshold_3 = ZH_TARIFF_RATES["tier_thresholds"][rates_key]
        
        if monthly_usage > threshold_3:
            tier_adder = ZH_TARIFF_RATES["tier_adders"][rates_key]["tier_3"]
        elif monthly_usage > threshold_2:
            tier_adder = ZH_TARIFF_RATES["tier_adders"][rates_key]["tier_2"]
        # else: tier_adder 保持 0.0 (Tier 1)

        # 5. 计算最终价格
        # 最终价格 = 基础电度电价 + 固定成本 + 阶梯加价
        final_price = base_rate + FIXED_COSTS + tier_adder
        
        self._state = round(final_price, 4)