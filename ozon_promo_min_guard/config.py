"""Загрузка и валидация конфигурации программы.

Конфигурация хранится в JSON-файле (по умолчанию ``config.json``) и содержит
креды доступа к OZON Seller API:

.. code-block:: json

    {
      "Ozon": {
        "ApiKey": "...",
        "ClientId": "..."
      }
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Ошибка загрузки или валидации конфигурации."""


@dataclass(frozen=True)
class OzonConfig:
    """Креды доступа к OZON Seller API."""

    api_key: str
    client_id: str


def load_config(path: str | Path = "config.json") -> OzonConfig:
    """Загрузить и провалидировать конфигурацию из JSON-файла.

    Args:
        path: путь к файлу конфигурации.

    Returns:
        Объект :class:`OzonConfig` с кредами доступа.

    Raises:
        ConfigError: если файл отсутствует, имеет неверный формат
            или не содержит обязательных полей.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigError(
            f"Файл конфигурации не найден: {config_path}. "
            "Скопируйте config.example.json в config.json и укажите свои креды."
        )

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Не удалось разобрать JSON в файле {config_path}: {exc}"
        ) from exc

    ozon = data.get("Ozon")
    if not isinstance(ozon, dict):
        raise ConfigError(
            "В конфигурации отсутствует секция 'Ozon' (объект с ApiKey и ClientId)."
        )

    api_key = ozon.get("ApiKey")
    client_id = ozon.get("ClientId")

    if not api_key or not isinstance(api_key, str):
        raise ConfigError("В секции 'Ozon' отсутствует или пуст 'ApiKey'.")
    if not client_id or not isinstance(client_id, str):
        raise ConfigError("В секции 'Ozon' отсутствует или пуст 'ClientId'.")

    return OzonConfig(api_key=api_key.strip(), client_id=client_id.strip())
