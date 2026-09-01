"""Формирование и чтение отчёта о найденных товарах.

Отчёт сохраняется в JSON и/или CSV файл и используется командой
``delete`` для определения списка товаров, которые нужно удалить
из акции.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .actions import ActionProduct

REPORT_FIELDS = [
    "action_id",
    "action_title",
    "product_id",
    "offer_id",
    "price",
    "min_seller_price",
    "difference",
    "source",
    "auto_add_date",
]


class ReportError(Exception):
    """Ошибка при работе с файлом отчёта."""


def save_report_json(products: list[ActionProduct], path: str | Path) -> Path:
    """Сохранить отчёт в JSON-файл.

    Returns:
        Путь к сохранённому файлу.
    """
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    data = [product.to_dict() for product in products]
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    return report_path


def save_report_csv(products: list[ActionProduct], path: str | Path) -> Path:
    """Сохранить отчёт в CSV-файл.

    Returns:
        Путь к сохранённому файлу.
    """
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for product in products:
            writer.writerow(product.to_dict())

    return report_path


def load_report(path: str | Path) -> list[dict[str, Any]]:
    """Загрузить отчёт из JSON или CSV файла.

    Формат определяется по расширению файла.

    Returns:
        Список записей отчёта (словарей).

    Raises:
        ReportError: если файл не найден или имеет неверный формат.
    """
    report_path = Path(path)

    if not report_path.exists():
        raise ReportError(f"Файл отчёта не найден: {report_path}")

    suffix = report_path.suffix.lower()

    if suffix == ".json":
        return _load_json(report_path)
    if suffix == ".csv":
        return _load_csv(report_path)

    raise ReportError(
        f"Неподдерживаемый формат отчёта '{suffix}'. "
        "Используйте .json или .csv."
    )


def _load_json(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ReportError(f"Не удалось разобрать JSON-отчёт {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ReportError(f"JSON-отчёт {path} должен содержать список записей.")

    return data


def _load_csv(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return [dict(row) for row in reader]
    except csv.Error as exc:
        raise ReportError(f"Не удалось разобрать CSV-отчёт {path}: {exc}") from exc
