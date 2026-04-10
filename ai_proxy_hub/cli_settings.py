from __future__ import annotations

from typing import TYPE_CHECKING

from .cli_settings_appearance import CliSettingsAppearanceMixin
from .cli_settings_general import CliSettingsGeneralMixin
from .cli_settings_network import CliSettingsNetworkMixin

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliSettingsController(
    CliSettingsNetworkMixin,
    CliSettingsAppearanceMixin,
    CliSettingsGeneralMixin,
):
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app


__all__ = ["CliSettingsController"]
