import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("name", default="Zhuhai Energy Price"): str,
    vol.Optional("tou_high", default=102.03): vol.Coerce(float),
    vol.Optional("tou_normal", default=82.01): vol.Coerce(float),
    vol.Optional("tou_low", default=62.81): vol.Coerce(float),
    vol.Optional("tier1", default=60.02): vol.Coerce(float),
    vol.Optional("tier2", default=65.02): vol.Coerce(float),
    vol.Optional("tier3", default=90.02): vol.Coerce(float),
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input.get("name", "Zhuhai Energy Price"), data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)
