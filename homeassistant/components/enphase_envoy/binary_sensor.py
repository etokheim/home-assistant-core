"""Support for Enphase Envoy solar energy monitor."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyenphase import EnvoyEncharge, EnvoyEnpower
from pyenphase.models.dry_contacts import DryContactStatus

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EnphaseUpdateCoordinator
from .entity import EnvoyBaseEntity


@dataclass
class EnvoyEnchargeRequiredKeysMixin:
    """Mixin for required keys."""

    value_fn: Callable[[EnvoyEncharge], bool]


@dataclass
class EnvoyEnchargeBinarySensorEntityDescription(
    BinarySensorEntityDescription, EnvoyEnchargeRequiredKeysMixin
):
    """Describes an Envoy Encharge binary sensor entity."""


ENCHARGE_SENSORS = (
    EnvoyEnchargeBinarySensorEntityDescription(
        key="communicating",
        translation_key="communicating",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda encharge: encharge.communicating,
    ),
    EnvoyEnchargeBinarySensorEntityDescription(
        key="dc_switch",
        translation_key="dc_switch",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda encharge: not encharge.dc_switch_off,
    ),
    EnvoyEnchargeBinarySensorEntityDescription(
        key="operating",
        translation_key="operating",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda encharge: encharge.operating,
    ),
)

RELAY_STATUS_SENSOR = BinarySensorEntityDescription(
    key="relay_status", icon="mdi:power-plug", has_entity_name=True
)


@dataclass
class EnvoyEnpowerRequiredKeysMixin:
    """Mixin for required keys."""

    value_fn: Callable[[EnvoyEnpower], bool]


@dataclass
class EnvoyEnpowerBinarySensorEntityDescription(
    BinarySensorEntityDescription, EnvoyEnpowerRequiredKeysMixin
):
    """Describes an Envoy Enpower binary sensor entity."""


ENPOWER_SENSORS = (
    EnvoyEnpowerBinarySensorEntityDescription(
        key="communicating",
        translation_key="communicating",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda enpower: enpower.communicating,
    ),
    EnvoyEnpowerBinarySensorEntityDescription(
        key="operating",
        translation_key="operating",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda enpower: enpower.operating,
    ),
    EnvoyEnpowerBinarySensorEntityDescription(
        key="mains_oper_state",
        translation_key="grid_status",
        icon="mdi:transmission-tower",
        value_fn=lambda enpower: enpower.mains_oper_state == "closed",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up envoy binary sensor platform."""
    coordinator: EnphaseUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    envoy_data = coordinator.envoy.data
    assert envoy_data is not None
    envoy_serial_num = config_entry.unique_id
    assert envoy_serial_num is not None
    entities: list[BinarySensorEntity] = []
    if envoy_data.encharge_inventory:
        entities.extend(
            EnvoyEnchargeBinarySensorEntity(coordinator, description, encharge)
            for description in ENCHARGE_SENSORS
            for encharge in envoy_data.encharge_inventory
        )

    if envoy_data.enpower:
        entities.extend(
            EnvoyEnpowerBinarySensorEntity(coordinator, description)
            for description in ENPOWER_SENSORS
        )

    if envoy_data.dry_contact_status:
        entities.extend(
            EnvoyRelayBinarySensorEntity(coordinator, RELAY_STATUS_SENSOR, relay)
            for relay in envoy_data.dry_contact_status
        )
    async_add_entities(entities)


class EnvoyBaseBinarySensorEntity(EnvoyBaseEntity, BinarySensorEntity):
    """Defines a base envoy binary_sensor entity."""


class EnvoyEnchargeBinarySensorEntity(EnvoyBaseBinarySensorEntity):
    """Defines an Encharge binary_sensor entity."""

    entity_description: EnvoyEnchargeBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EnphaseUpdateCoordinator,
        description: EnvoyEnchargeBinarySensorEntityDescription,
        serial_number: str,
    ) -> None:
        """Init the Encharge base entity."""
        super().__init__(coordinator, description)
        self._serial_number = serial_number
        self._attr_unique_id = f"{serial_number}_{description.key}"
        encharge_inventory = self.data.encharge_inventory
        assert encharge_inventory is not None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer="Enphase",
            model="Encharge",
            name=f"Encharge {serial_number}",
            sw_version=str(encharge_inventory[self._serial_number].firmware_version),
            via_device=(DOMAIN, self.envoy_serial_num),
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the Encharge binary_sensor."""
        encharge_inventory = self.data.encharge_inventory
        assert encharge_inventory is not None
        return self.entity_description.value_fn(encharge_inventory[self._serial_number])


class EnvoyEnpowerBinarySensorEntity(EnvoyBaseBinarySensorEntity):
    """Defines an Enpower binary_sensor entity."""

    entity_description: EnvoyEnpowerBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EnphaseUpdateCoordinator,
        description: EnvoyEnpowerBinarySensorEntityDescription,
    ) -> None:
        """Init the Enpower base entity."""
        super().__init__(coordinator, description)
        enpower = self.data.enpower
        assert enpower is not None
        self._serial_number = enpower.serial_number
        self._attr_unique_id = f"{self._serial_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._serial_number)},
            manufacturer="Enphase",
            model="Enpower",
            name=f"Enpower {self._serial_number}",
            sw_version=str(enpower.firmware_version),
            via_device=(DOMAIN, self.envoy_serial_num),
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the Enpower binary_sensor."""
        enpower = self.data.enpower
        assert enpower is not None
        return self.entity_description.value_fn(enpower)


class EnvoyRelayBinarySensorEntity(EnvoyBaseBinarySensorEntity):
    """Defines an Enpower dry contact binary_sensor entity."""

    def __init__(
        self,
        coordinator: EnphaseUpdateCoordinator,
        description: BinarySensorEntityDescription,
        relay_id: str,
    ) -> None:
        """Init the Enpower base entity."""
        super().__init__(coordinator, description)
        enpower = self.data.enpower
        assert enpower is not None
        self.relay_id = relay_id
        self._serial_number = enpower.serial_number
        self._attr_unique_id = f"{self._serial_number}_relay_{relay_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._serial_number)},
            manufacturer="Enphase",
            model="Enpower",
            name=f"Enpower {self._serial_number}",
            sw_version=str(enpower.firmware_version),
            via_device=(DOMAIN, self.envoy_serial_num),
        )
        self._attr_name = f"{self.data.dry_contact_settings[relay_id].load_name} Relay"

    @property
    def is_on(self) -> bool:
        """Return the state of the Enpower binary_sensor."""
        relay = self.data.dry_contact_status[self.relay_id]
        return relay.status == DryContactStatus.CLOSED
