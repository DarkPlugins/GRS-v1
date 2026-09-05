"""Loading and validating the runtime configuration."""

from __future__ import annotations

import copy
import json
import os
from typing import Any


DEFAULT_SETTINGS = {
    "logging": {
        "enabled": True,
    },
    "bluetooth": {
        "targets": ["n-m405"],
        "scan_interval": 5,
    },
    "encoder": {
        "clk_pin": 5,
        "dt_pin": 6,
        "sw_pin": 23,
        "rotary_bounce_time": 0.003,
        "button_bounce_time": 0.05,
    },
    "lcd": {
        "spi_bus": 0,
        "spi_device": 0,
        "spi_freq": 40000000,
        "rst": 27,
        "dc": 25,
        "bl": 18,
        "tp_int": 4,
        "tp_rst": 17,
        "bl_freq": 1000,
    },
}


class Settings:
    """Read ``lib/settings.json`` and expose validated settings sections."""

    CONFIG_FILENAME = "settings.json"
    LAST_RUN_FILENAME = "last_run.json"

    def __init__(self, root_path: str):
        self.root_path = os.path.abspath(root_path)
        self.config_path = os.path.join(self.root_path, "lib", self.CONFIG_FILENAME)
        self.last_run_path = os.path.join(self.root_path, "lib", self.LAST_RUN_FILENAME)
        self.warnings: list[str] = []
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.config_path):
            self.warnings.append(f"Settings file not found: {self.config_path}; using defaults.")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            self.warnings.append(f"Could not read settings file '{self.config_path}': {exc}; using defaults.")
            return

        # Before settings.json was introduced, this file stored the last song.
        # Move that legacy object to its new location once during an upgrade.
        if self._is_legacy_last_run(loaded):
            if not os.path.exists(self.last_run_path):
                try:
                    os.replace(self.config_path, self.last_run_path)
                    self.warnings.append(
                        f"Migrated legacy state file to {self.last_run_path}."
                    )
                    return
                except OSError as exc:
                    self.warnings.append(f"Could not migrate legacy state file: {exc}; using defaults.")
            else:
                self.warnings.append(
                    "Legacy settings.json detected while last_run.json already exists; using last_run.json."
                )
            return

        if not isinstance(loaded, dict):
            self.warnings.append("Settings file must contain a JSON object; using defaults.")
            return

        self._merge(self.data, loaded)
        self._validate()

    @staticmethod
    def _is_legacy_last_run(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and "game_name" in value
            and "song_name" in value
            and not any(section in value for section in DEFAULT_SETTINGS)
        )

    @classmethod
    def _merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(target.get(key), dict) and isinstance(value, dict):
                cls._merge(target[key], value)
            else:
                target[key] = value

    def _validate(self) -> None:
        self._validate_logging()
        self._validate_bluetooth()
        self._validate_section(
            "encoder",
            integer_keys=("clk_pin", "dt_pin", "sw_pin"),
            float_keys=("rotary_bounce_time", "button_bounce_time"),
        )
        self._validate_section(
            "lcd",
            integer_keys=("spi_bus", "spi_device", "spi_freq", "rst", "dc", "bl", "tp_int", "tp_rst", "bl_freq"),
            float_keys=(),
        )

    def _validate_logging(self) -> None:
        section = self.data.get("logging")
        if not isinstance(section, dict) or not isinstance(section.get("enabled"), bool):
            self.data["logging"] = copy.deepcopy(DEFAULT_SETTINGS["logging"])
            self.warnings.append("Invalid logging settings; using defaults.")

    def _validate_bluetooth(self) -> None:
        section = self.data.get("bluetooth")
        if not isinstance(section, dict):
            self.data["bluetooth"] = copy.deepcopy(DEFAULT_SETTINGS["bluetooth"])
            self.warnings.append("Invalid Bluetooth settings; using defaults.")
            return

        targets = section.get("targets")
        if not isinstance(targets, list) or not targets or any(
            not isinstance(target, str) or not target.strip() for target in targets
        ):
            section["targets"] = copy.deepcopy(DEFAULT_SETTINGS["bluetooth"]["targets"])
            self.warnings.append("Invalid Bluetooth targets; using defaults.")
        else:
            section["targets"] = [target.strip().lower() for target in targets]

        interval = section.get("scan_interval")
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0:
            section["scan_interval"] = DEFAULT_SETTINGS["bluetooth"]["scan_interval"]
            self.warnings.append("Invalid Bluetooth scan interval; using default.")
        else:
            section["scan_interval"] = max(1, int(interval))

    def _validate_section(self, name: str, integer_keys, float_keys) -> None:
        section = self.data.get(name)
        defaults = DEFAULT_SETTINGS[name]
        if not isinstance(section, dict):
            self.data[name] = copy.deepcopy(defaults)
            self.warnings.append(f"Invalid {name} settings; using defaults.")
            return

        for key in integer_keys:
            value = section.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                section[key] = defaults[key]
                self.warnings.append(f"Invalid {name}.{key}; using default.")

        for key in float_keys:
            value = section.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                section[key] = defaults[key]
                self.warnings.append(f"Invalid {name}.{key}; using default.")

    @property
    def logging_enabled(self) -> bool:
        return self.data["logging"]["enabled"]

    @property
    def bluetooth_targets(self) -> list[str]:
        return list(self.data["bluetooth"]["targets"])

    @property
    def bluetooth_scan_interval(self) -> int:
        return self.data["bluetooth"]["scan_interval"]

    @property
    def encoder(self) -> dict[str, Any]:
        return dict(self.data["encoder"])

    @property
    def lcd(self) -> dict[str, Any]:
        return dict(self.data["lcd"])
