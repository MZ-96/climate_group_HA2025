import itertools
import logging
from collections import Counter
from typing import List, Optional, Iterator, Any, Callable

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components import climate
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    UnitOfTemperature,
    CONF_TEMPERATURE_UNIT,
    CONF_ENTITIES,
    CONF_NAME,
    ATTR_SUPPORTED_FEATURES,
)
from homeassistant.core import State, callback
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.typing import HomeAssistantType, ConfigType

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Climate Group"
CONF_EXCLUDE = "exclude"

# Schema: manteniamo compatibilità, ma non vincoliamo i preset a una lista fissa
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TEMPERATURE_UNIT, default=str(UnitOfTemperature.CELSIUS)): cv.string,
        vol.Required(CONF_ENTITIES): cv.entities_domain(climate.DOMAIN),
        vol.Optional(CONF_EXCLUDE, default=[]): vol.All(cv.ensure_list, [cv.string]),
    }
)

# Feature supportate dal gruppo (limitiamo alle più utili/robuste)
SUPPORT_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.SWING_MODE
    | ClimateEntityFeature.FAN_MODE
)

# Ordine di priorità per hvac_action
HVAC_ACTIONS = [
    HVACAction.HEATING,
    HVACAction.COOLING,
    HVACAction.DRYING,
    HVACAction.FAN,
    HVACAction.IDLE,
    HVACAction.OFF,
    None,
]

# --- helper costanti attributi (evitiamo import che cambiano spesso) ---
ATTR_HVAC_MODE = "hvac_mode"
ATTR_HVAC_ACTION = "hvac_action"
ATTR_HVAC_MODES = "hvac_modes"
ATTR_FAN_MODE = "fan_mode"
ATTR_FAN_MODES = "fan_modes"
ATTR_SWING_MODE = "swing_mode"
ATTR_SWING_MODES = "swing_modes"
ATTR_PRESET_MODE = "preset_mode"
ATTR_PRESET_MODES = "preset_modes"
ATTR_MIN_TEMP = "min_temp"
ATTR_MAX_TEMP = "max_temp"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_TARGET_TEMP_LOW = "target_temp_low"
ATTR_TARGET_TEMP_HIGH = "target_temp_high"


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Initialize climate_group_custom platform."""
    async_add_entities(
        [
            ClimateGroupCustom(
                config.get(CONF_NAME),
                config[CONF_ENTITIES],
                config.get(CONF_EXCLUDE),
                config.get(CONF_TEMPERATURE_UNIT),
            )
        ]
    )


class ClimateGroupCustom(ClimateEntity):
    """Representation of a climate group (custom, HA 2025-ready)."""

    def __init__(self, name: str, entity_ids: List[str], excluded: List[str], unit: str) -> None:
        self._name = name
        self._entity_ids = entity_ids
        if "c" in unit.lower():
            self._unit = UnitOfTemperature.CELSIUS
        else:
            self._unit = UnitOfTemperature.FAHRENHEIT

        self._min_temp = 0
        self._max_temp = 0
        self._current_temp: Optional[float] = None
        self._target_temp: Optional[float] = None
        self._target_temp_high: Optional[float] = None
        self._target_temp_low: Optional[float] = None

        self._mode: Optional[HVACMode] = None
        self._action: Optional[HVACAction] = None
        self._mode_list: Optional[List[HVACMode]] = None
        self._available = True
        self._supported_features = 0

        self._async_unsub_state_changed = None

        self._fan_modes = None
        self._fan_mode = None
        self._swing_modes = None
        self._swing_mode = None
        self._preset_modes = None
        self._preset = None
        self._excluded = excluded or []

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        @callback
        def async_state_changed_listener(entity_id: str, old_state: State, new_state: State):
            self.async_schedule_update_ha_state(True)

        self._async_unsub_state_changed = async_track_state_change(
            self.hass, self._entity_ids, async_state_changed_listener
        )
        await self.async_update()

    async def async_will_remove_from_hass(self):
        if self._async_unsub_state_changed is not None:
            self._async_unsub_state_changed()
            self._async_unsub_state_changed = None

    # --------- properties base ---------
    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return self._available

    @property
    def supported_features(self) -> int:
        return self._supported_features

    @property
    def hvac_mode(self) -> Optional[HVACMode]:
        return self._mode

    @property
    def hvac_action(self) -> Optional[HVACAction]:
        return self._action

    @property
    def hvac_modes(self) -> Optional[List[HVACMode]]:
        return self._mode_list

    @property
    def min_temp(self) -> float:
        return self._min_temp

    @property
    def max_temp(self) -> float:
        return self._max_temp

    @property
    def current_temperature(self) -> Optional[float]:
        return self._current_temp

    @property
    def target_temperature(self) -> Optional[float]:
        return self._target_temp

    @property
    def target_temperature_low(self) -> Optional[float]:
        return self._target_temp_low

    @property
    def target_temperature_high(self) -> Optional[float]:
        return self._target_temp_high

    @property
    def temperature_unit(self):
        return self._unit

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def extra_state_attributes(self):
        return {ATTR_ENTITY_ID: self._entity_ids}

    # --------- set* (comandi) ---------
    async def async_set_temperature(self, **kwargs):
        data = {ATTR_ENTITY_ID: self._entity_ids}
        if ATTR_HVAC_MODE in kwargs:
            await self.async_set_hvac_mode(kwargs[ATTR_HVAC_MODE])
            return

        if (
            ATTR_TEMPERATURE in kwargs
            or ATTR_TARGET_TEMP_LOW in kwargs
            or ATTR_TARGET_TEMP_HIGH in kwargs
        ):
            if ATTR_TEMPERATURE in kwargs:
                data[ATTR_TEMPERATURE] = kwargs[ATTR_TEMPERATURE]
            else:
                if ATTR_TARGET_TEMP_LOW in kwargs:
                    data[ATTR_TARGET_TEMP_LOW] = kwargs[ATTR_TARGET_TEMP_LOW]
                if ATTR_TARGET_TEMP_HIGH in kwargs:
                    data[ATTR_TARGET_TEMP_HIGH] = kwargs[ATTR_TARGET_TEMP_HIGH]

            await self.hass.services.async_call(
                climate.DOMAIN, climate.SERVICE_SET_TEMPERATURE, data, blocking=True
            )

    async def async_set_hvac_mode(self, hvac_mode):
        # accetta sia stringa che HVACMode
        mode_value = hvac_mode.value if isinstance(hvac_mode, HVACMode) else hvac_mode
        await self.hass.services.async_call(
            climate.DOMAIN,
            climate.SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: self._entity_ids, ATTR_HVAC_MODE: mode_value},
            blocking=True,
        )

    async def async_set_fan_mode(self, fan_mode: str):
        await self.hass.services.async_call(
            climate.DOMAIN,
            climate.SERVICE_SET_FAN_MODE,
            {ATTR_ENTITY_ID: self._entity_ids, ATTR_FAN_MODE: fan_mode},
            blocking=True,
        )

    async def async_set_swing_mode(self, swing_mode: str):
        await self.hass.services.async_call(
            climate.DOMAIN,
            climate.SERVICE_SET_SWING_MODE,
            {ATTR_ENTITY_ID: self._entity_ids, ATTR_SWING_MODE: swing_mode},
            blocking=True,
        )

    async def async_set_preset_mode(self, preset_mode: str):
        await self.hass.services.async_call(
            climate.DOMAIN,
            climate.SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: self._entity_ids, ATTR_PRESET_MODE: preset_mode},
            blocking=True,
        )

    # --------- update aggregato ---------
    async def async_update(self):
        raw_states = [self.hass.states.get(x) for x in self._entity_ids]
        states = [s for s in raw_states if s is not None]

        # filtra per preset esclusi (se configurati)
        filtered_states = [
            s for s in states if s.attributes.get(ATTR_PRESET_MODE) not in self._excluded
        ]
        if not filtered_states:
            filtered_states = states

        # hvac_mode aggregato (priorità)
        all_modes_raw = [s.state for s in filtered_states]
        preferred_order = [
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.HEAT_COOL,
            HVACMode.AUTO,
            HVACMode.OFF,
        ]
        self._mode = None
        for m in preferred_order:
            if any(mode == m.value for mode in all_modes_raw):
                self._mode = m
                break

        # hvac_action aggregata (priorità)
        all_actions_raw = [s.attributes.get(ATTR_HVAC_ACTION) for s in filtered_states]
        self._action = None
        for act in HVAC_ACTIONS:
            val = act.value if isinstance(act, HVACAction) else act
            if any(a == val for a in all_actions_raw):
                self._action = act if isinstance(act, HVACAction) else None
                break

        # fan / swing / preset (valore più comune)
        all_fan_modes = [s.attributes.get(ATTR_FAN_MODE) for s in filtered_states]
        self._fan_mode = Counter(itertools.chain(all_fan_modes)).most_common(1)[0][0] if all_fan_modes else None

        all_swing_modes = [s.attributes.get(ATTR_SWING_MODE) for s in filtered_states]
        self._swing_mode = Counter(itertools.chain(all_swing_modes)).most_common(1)[0][0] if all_swing_modes else None

        all_presets = [s.attributes.get(ATTR_PRESET_MODE) for s in filtered_states]
        self._preset = Counter(itertools.chain(all_presets)).most_common(1)[0][0] if all_presets else None

        # temperature/limiti aggregati
        self._target_temp = _reduce_attribute(filtered_states, ATTR_TEMPERATURE)
        self._target_temp_low = _reduce_attribute(filtered_states, ATTR_TARGET_TEMP_LOW)
        self._target_temp_high = _reduce_attribute(filtered_states, ATTR_TARGET_TEMP_HIGH)
        self._current_temp = _reduce_attribute(filtered_states, ATTR_CURRENT_TEMPERATURE)

        self._min_temp = _reduce_attribute(states, ATTR_MIN_TEMP, reduce=max, default=0) or 0
        self._max_temp = _reduce_attribute(states, ATTR_MAX_TEMP, reduce=min, default=0) or 0

        # hvac_modes disponibili (unione)
        self._mode_list = None
        mode_lists = list(_find_state_attributes(states, ATTR_HVAC_MODES))
        if mode_lists:
            # unione e conversione a HVACMode, ignorando valori ignoti
            raw = set().union(*mode_lists)
            converted = []
            for v in raw:
                try:
                    converted.append(HVACMode(v))
                except Exception:
                    pass
            self._mode_list = converted or [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]

        # supported_features aggregati
        self._supported_features = 0
        for support in _find_state_attributes(states, ATTR_SUPPORTED_FEATURES):
            self._supported_features |= support
        self._supported_features &= SUPPORT_FLAGS

        # liste fan/swing/preset (unione)
        fan_modes = []
        for fm in _find_state_attributes(states, ATTR_FAN_MODES):
            fan_modes.extend(fm)
        self._fan_modes = list(set(fan_modes)) if fan_modes else None

        swing_modes = []
        for sm in _find_state_attributes(states, ATTR_SWING_MODES):
            swing_modes.extend(sm)
        self._swing_modes = list(set(swing_modes)) if swing_modes else None

        presets = []
        for pm in _find_state_attributes(states, ATTR_PRESET_MODES):
            presets.extend(pm)
        self._preset_modes = list(set(presets)) if presets else None

        _LOGGER.debug(
            "Update complete | mode=%s action=%s t=%.2f t_low=%s t_high=%s cur=%.2f",
            getattr(self._mode, "value", self._mode),
            getattr(self._action, "value", self._action),
            self._target_temp or -1,
            self._target_temp_low,
            self._target_temp_high,
            self._current_temp or -1,
        )

    # proprietà opzionali per UI
    @property
    def fan_mode(self):
        return self._fan_mode

    @property
    def fan_modes(self):
        return self._fan_modes

    @property
    def swing_mode(self):
        return self._swing_mode

    @property
    def swing_modes(self):
        return self._swing_modes

    @property
    def preset_mode(self):
        return self._preset

    @property
    def preset_modes(self):
        return self._preset_modes


def _find_state_attributes(states: List[State], key: str) -> Iterator[Any]:
    for state in states:
        value = state.attributes.get(key)
        if value is not None:
            yield value


def _mean(*args):
    return sum(args) / len(args)


def _reduce_attribute(
    states: List[State],
    key: str,
    default: Optional[Any] = None,
    reduce: Callable[..., Any] = _mean,
) -> Any:
    attrs = list(_find_state_attributes(states, key))
    if not attrs:
        return default
    if len(attrs) == 1:
        return attrs[0]
    return reduce(*attrs)
