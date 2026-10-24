"""Логика работы с промоакциями OZON.

Содержит функции для получения списка акций, товаров в акциях,
поиска товаров, продающихся дешевле минимальной цены,
и удаления товаров из акции.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Literal

from .client import OzonApiError, OzonClient

ProductSource = Literal["participating", "auto_add"]


@dataclass
class ActionProduct:
    """Товар в акции с данными, необходимыми для анализа и удаления."""

    action_id: int
    action_title: str
    product_id: int
    offer_id: str
    price: float
    min_seller_price: float
    auto_add_date: str = ""
    source: ProductSource = "participating"

    @property
    def difference(self) -> float:
        """Насколько цена в акции ниже минимальной цены (положительное число)."""
        return self.min_seller_price - self.price

    @property
    def is_below_min_price(self) -> bool:
        """True, если цена в акции ниже минимальной цены."""
        return self.min_seller_price > 0 and self.price < self.min_seller_price

    def to_dict(self) -> dict[str, Any]:
        """Представить товар в виде словаря для отчёта."""
        return {
            "action_id": self.action_id,
            "action_title": self.action_title,
            "product_id": self.product_id,
            "offer_id": self.offer_id,
            "price": self.price,
            "min_seller_price": self.min_seller_price,
            "difference": round(self.difference, 2),
            "auto_add_date": self.auto_add_date,
            "source": self.source,
        }


def _as_float(value: Any) -> float | None:
    """Привести значение к float; None и пустые значения — в None.

    Метод ``/v2/actions/auto-add/products/list`` отдаёт цены объектом
    ``{"amount": "1176", "currency": "RUB"}``, старые ответы — числом.
    """
    if isinstance(value, dict):
        value = value.get("amount")
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_actions(client: OzonClient) -> list[dict[str, Any]]:
    """Получить список промоакций."""
    return client.get_actions()


def _find_participating_below_min(
    client: OzonClient,
    actions: list[dict[str, Any]],
    seen: set[tuple[int, int]],
) -> list[ActionProduct]:
    """Найти участвующие в акциях товары с ценой ниже минимальной.

    Соответствует тому, что показывает интерфейс OZON («Цена по этой акции»
    vs «Минимальная цена», метка «Ниже минимальной»).
    """
    found: list[ActionProduct] = []

    for action in actions:
        action_id = action.get("id")
        if action_id is None:
            continue

        action_title = action.get("title") or action.get("name") or str(action_id)
        products = client.get_action_products(int(action_id))
        if not products:
            continue

        product_ids = [
            int(product["id"])
            for product in products
            if product.get("id") is not None
        ]
        price_info = client.get_product_price_info(product_ids)

        for product in products:
            product_id_raw = product.get("id")
            if product_id_raw is None:
                continue

            product_id = int(product_id_raw)
            key = (int(action_id), product_id)
            if key in seen:
                continue

            action_price = _as_float(product.get("action_price"))
            info = price_info.get(product_id)
            if action_price is None or info is None or info.min_price <= 0:
                continue

            offer_id = str(product.get("offer_id") or info.offer_id or "")

            item = ActionProduct(
                action_id=int(action_id),
                action_title=str(action_title),
                product_id=product_id,
                offer_id=offer_id,
                price=action_price,
                min_seller_price=info.min_price,
                source="participating",
            )

            if item.is_below_min_price:
                seen.add(key)
                found.append(item)

    return found


def _find_auto_add_below_min(
    client: OzonClient,
    actions: list[dict[str, Any]],
    seen: set[tuple[int, int]],
) -> list[ActionProduct]:
    """Найти товары в очереди авто-добавления с ценой ниже минимальной."""
    found: list[ActionProduct] = []

    for action in actions:
        action_id = action.get("id")
        action_title = action.get("title") or action.get("name") or str(action_id)
        auto_add_dates = action.get("auto_add_dates") or []

        if action_id is None or not auto_add_dates:
            continue

        for auto_add_date in auto_add_dates:
            try:
                products = client.get_auto_add_products(int(action_id), auto_add_date)
            except OzonApiError as exc:
                if "blocked" in str(exc).lower():
                    print(
                        "Предупреждение: OZON заблокировал метод очереди "
                        "авто-добавления (логика единой цены). Очередь "
                        "авто-добавления не проверяется.",
                        file=sys.stderr,
                    )
                    return found
                print(
                    f"Предупреждение: не удалось получить очередь "
                    f"авто-добавления акции {action_id}: {exc}",
                    file=sys.stderr,
                )
                continue

            for product in products:
                product_id_raw = product.get("product_id")
                if product_id_raw is None:
                    continue

                product_id = int(product_id_raw)
                key = (int(action_id), product_id)
                if key in seen:
                    continue

                price = _as_float(product.get("action_price_to_auto_add"))
                min_price = _as_float(product.get("min_seller_price"))
                if price is None or min_price is None or min_price <= 0:
                    continue

                item = ActionProduct(
                    action_id=int(action_id),
                    action_title=str(action_title),
                    product_id=product_id,
                    offer_id=str(product.get("offer_id", "")),
                    price=price,
                    min_seller_price=min_price,
                    auto_add_date=auto_add_date,
                    source="auto_add",
                )

                if item.is_below_min_price:
                    seen.add(key)
                    found.append(item)

    return found


def find_products_below_min_price(
    client: OzonClient,
    actions: list[dict[str, Any]] | None = None,
) -> list[ActionProduct]:
    """Найти товары, продающиеся в акции дешевле минимальной цены.

    Проверяются два источника:

    1. **Участвующие товары** — ``POST /v1/actions/products`` +
       ``POST /v5/product/info/prices``. Совпадает с интерфейсом OZON
       (колонка «Цена по этой акции» vs «Минимальная цена»).
    2. **Очередь авто-добавления** — ``POST /v2/actions/auto-add/products/list``.
       Товары, которые ещё не в акции, но будут добавлены по заниженной цене.

    Args:
        client: клиент OZON API.
        actions: список акций; если не передан, будет получен автоматически.

    Returns:
        Список :class:`ActionProduct` с товарами ниже минимальной цены.
    """
    if actions is None:
        actions = get_actions(client)

    seen: set[tuple[int, int]] = set()
    found = _find_participating_below_min(client, actions, seen)
    found.extend(_find_auto_add_below_min(client, actions, seen))
    return found


def delete_products_from_action(
    client: OzonClient,
    products: list[ActionProduct],
) -> dict[str, dict[str, Any]]:
    """Удалить товары из акций.

    Участвующие товары удаляются через ``/v1/actions/products/deactivate``,
    товары из очереди авто-добавления — через
    ``/v2/actions/auto-add/products/delete``.

    Ошибка API для одной группы не прерывает удаление остальных.

    Args:
        client: клиент OZON API.
        products: список товаров для удаления.

    Returns:
        Словарь: ключ группы -> ответ API.
    """
    results: dict[str, dict[str, Any]] = {}

    participating: dict[int, list[int]] = {}
    auto_add: dict[tuple[int, str], list[int]] = {}

    for product in products:
        source = product.source
        if not source and product.auto_add_date:
            source = "auto_add"
        elif not source:
            source = "participating"

        if source == "auto_add":
            key = (product.action_id, product.auto_add_date)
            auto_add.setdefault(key, []).append(product.product_id)
        else:
            participating.setdefault(product.action_id, []).append(product.product_id)

    for action_id, product_ids in participating.items():
        group_key = f"participating:{action_id}"
        try:
            results[group_key] = client.deactivate_action_products(
                action_id, product_ids
            )
        except OzonApiError as exc:
            results[group_key] = {"error": str(exc)}

    for (action_id, auto_add_date), product_ids in auto_add.items():
        group_key = f"auto_add:{action_id}:{auto_add_date}"
        try:
            results[group_key] = client.delete_action_products(
                action_id, auto_add_date, product_ids
            )
        except OzonApiError as exc:
            results[group_key] = {"error": str(exc)}

    return results
