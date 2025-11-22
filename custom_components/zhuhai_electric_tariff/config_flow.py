# config_flow.py

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_NAME

from .const import DOMAIN, CONF_ENERGY_SENSOR_ID

class ZhuhaiTariffConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """珠海电价集成的配置流."""

    VERSION = 1
    
    # 允许一次只添加一个实例
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZhuhaiTariffOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """处理用户初始化配置."""
        errors = {}
        if user_input is not None:
            # 简单验证用户是否输入了传感器ID
            if not user_input.get(CONF_ENERGY_SENSOR_ID):
                errors["base"] = "missing_sensor_id"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        # 用户的输入表单
        data_schema = vol.Schema({
            vol.Required(CONF_NAME, default="Zhuhai Tariff"): str,
            vol.Required(CONF_ENERGY_SENSOR_ID): str,
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )

class ZhuhaiTariffOptionsFlow(config_entries.OptionsFlow):
    """处理集成的选项."""

    def __init__(self, config_entry):
        """初始化选项流程."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """管理选项."""
        # 用户的选项表单 (例如修改传感器ID)
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Required(
                CONF_ENERGY_SENSOR_ID, 
                default=self.config_entry.data.get(CONF_ENERGY_SENSOR_ID)
            ): str,
        })

        return self.async_show_form(
            step_id="init", 
            data_schema=options_schema
        )
