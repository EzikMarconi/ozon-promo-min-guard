"""CLI-интерфейс программы.

Подкоманды:
    check  — проверить акции и найти товары дешевле минимальной цены.
    delete — удалить товары из акции по списку из отчёта.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .actions import (
    ActionProduct,
    delete_products_from_action,
    find_products_below_min_price,
    get_actions,
)
from .client import OzonApiError, OzonClient
from .config import ConfigError, load_config
from .report import ReportError, load_report, save_report_csv, save_report_json

DEFAULT_CONFIG = "config.json"
DEFAULT_REPORT_JSON = "report.json"
DEFAULT_REPORT_CSV = "report.csv"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ozon-promo-min-guard",
        description="Поиск и удаление товаров в акциях OZON ниже минимальной цены.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Путь к файлу конфигурации (по умолчанию: {DEFAULT_CONFIG}).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- check ---
    check_parser = subparsers.add_parser(
        "check", help="Проверить акции и найти товары дешевле минимальной цены."
    )
    check_parser.add_argument(
        "--json",
        default=DEFAULT_REPORT_JSON,
        help=f"Путь к JSON-отчёту (по умолчанию: {DEFAULT_REPORT_JSON}).",
    )
    check_parser.add_argument(
        "--csv",
        default=DEFAULT_REPORT_CSV,
        help=f"Путь к CSV-отчёту (по умолчанию: {DEFAULT_REPORT_CSV}).",
    )
    check_parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Не сохранять CSV-отчёт.",
    )

    # --- delete ---
    delete_parser = subparsers.add_parser(
        "delete", help="Удалить товары из акции по списку из отчёта."
    )
    delete_parser.add_argument(
        "report",
        help="Путь к файлу отчёта (JSON или CSV), созданному командой check.",
    )
    delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Удалять без запроса подтверждения.",
    )

    return parser


def _make_client(config_path: str) -> OzonClient:
    config = load_config(config_path)
    return OzonClient(config)


def _cmd_check(args: argparse.Namespace) -> int:
    client = _make_client(args.config)

    print("Получение списка акций OZON...")
    actions = get_actions(client)
    print(f"Найдено акций: {len(actions)}")

    print("Анализ товаров в акциях...")
    found = find_products_below_min_price(client, actions)

    if not found:
        print("Товаров дешевле минимальной цены не найдено.")
        return 0

    print(f"\nНайдено товаров дешевле минимальной цены: {len(found)}\n")
    _print_products(found)

    json_path = save_report_json(found, args.json)
    print(f"\nJSON-отчёт сохранён: {json_path}")

    if not args.no_csv:
        csv_path = save_report_csv(found, args.csv)
        print(f"CSV-отчёт сохранён: {csv_path}")

    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    client = _make_client(args.config)

    try:
        records = load_report(args.report)
    except ReportError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if not records:
        print("Отчёт пуст — удалять нечего.")
        return 0

    products = [_record_to_product(record) for record in records]

    print(f"Будет удалено товаров: {len(products)}")
    _print_products(products)

    if not args.yes:
        answer = input("Продолжить удаление? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            print("Удаление отменено.")
            return 0

    print("\nУдаление товаров из акций...")
    results = delete_products_from_action(client, products)

    for group_key, response in results.items():
        print(f"{group_key}: ответ API {response}")

    print("\nГотово.")
    return 0


def _record_to_product(record: dict) -> ActionProduct:
    """Преобразовать запись отчёта в объект :class:`ActionProduct`."""
    source = str(record.get("source", "")).strip()
    auto_add_date = str(record.get("auto_add_date", ""))
    if not source:
        source = "auto_add" if auto_add_date else "participating"

    return ActionProduct(
        action_id=int(record.get("action_id", 0)),
        action_title=str(record.get("action_title", "")),
        product_id=int(record.get("product_id", 0)),
        offer_id=str(record.get("offer_id", "")),
        price=float(record.get("price", 0.0)),
        min_seller_price=float(record.get("min_seller_price", 0.0)),
        auto_add_date=auto_add_date,
        source=source,  # type: ignore[arg-type]
    )


def _print_products(products: list[ActionProduct]) -> None:
    """Вывести список товаров в консоль в виде таблицы."""
    header = (
        f"{'Акция':<10} {'Товар':<12} {'Артикул':<20} "
        f"{'Цена':>10} {'Мин. цена':>10} {'Разница':>10}"
    )
    print(header)
    print("-" * len(header))
    for product in products:
        print(
            f"{product.action_id:<10} {product.product_id:<12} "
            f"{product.offer_id:<20} {product.price:>10.2f} "
            f"{product.min_seller_price:>10.2f} {product.difference:>10.2f}"
        )


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "delete":
            return _cmd_delete(args)
    except (ConfigError, OzonApiError, ReportError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
