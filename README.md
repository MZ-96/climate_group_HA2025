# MZ-96 Climate Group Custom

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

### Groups multiple climate devices into a single controllable entity (Home Assistant 2025+ compatible)

This custom integration allows you to group multiple climate devices into a single virtual climate entity, keeping full control over **temperature**, **HVAC modes**, **fan modes**, **swing modes**, and **presets**.  
It is based on the original `climate_group` component, updated and fixed for **Home Assistant Core 2025.x** (removed deprecated constants, updated API calls, and renamed to avoid conflicts).

---

## ✨ Features
- Full support for **Home Assistant 2025+**.
- Works with **heat**, **cool**, and **off** modes.
- Supports **fan_mode**, **swing_mode**, and **preset_mode** forwarding to all grouped devices.
- Aggregates **current temperature** and **target temperature**.
- Chooses the **most common HVAC mode** when turning on.
- Allows exclusion of specific preset modes from aggregation.
- Custom name and unit configuration.
- Keeps the **same YAML configuration style** as the original climate_group.

---

## 📜 Changelog

### 2.0.0 (MZ-96 release)
- Updated for Home Assistant 2025+ (removed deprecated `HVAC_MODE_*` constants, replaced with `HVACMode` enum).
- Renamed integration folder to `climate_group_custom` to avoid conflicts with older versions.
- Preserves all features from the original component.
- Fully compatible with Lovelace `thermostat` and custom cards (e.g., Mushroom).

---

## 📦 Manual Installation

1. Download or clone this repository.
2. Copy the folder: climate_group_custom
3. into your Home Assistant `config/custom_components` directory.
3. Restart Home Assistant.

---

## ⚙️ Configuration

Add this to your `configuration.yaml`:

```yaml
climate:
- platform: climate_group_custom
 name: "Daikin Main Group"
 temperature_unit: C             # optional: C / F        [default: C]
 entities:
    - climate.clima1
    - climate.clima2
    - climate.clima3
    - climate.clima4
    - climate.clima5
```
---

## 🖼 Example Lovelace Card
Here’s a Mushroom-based Lovelace configuration that uses the new group:

```yaml
 - type: thermostat
    entity: climate.daikin_main_group
    features:
      - type: climate-hvac-modes
        style: icons
        hvac_modes:
          - heat
          - cool
          - "off"
      - style: dropdown
        type: climate-fan-modes
        fan_modes:
          - auto
          - quiet
          - "1"
          - "2"
          - "3"
          - "4"
          - "5"
    show_current_as_primary: true
    theme: Mushroom
    name: Daikin Main Group
```

---

## 📄 Credits

Based on @bjrnptrsn/climate_group and @daenny/climate_group

