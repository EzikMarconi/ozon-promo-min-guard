"""HTTP-клиент для OZON Seller API.

Отвечает за формирование запросов с нужными заголовками
(``Client-Id``, ``Api-Key``), обработку ошибок и пагинацию.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import OzonConfig

API_BASE_URL = "https://api-seller.ozon.ru"


@dataclass(frozen=True)
class ProductPriceInfo:
    """Минимальная цена и артикул товара из API цен."""

    min_price: float
    offer_id: str = ""


class OzonApiError(Exception):
    """Ошибка при выполнении запроса к OZON API."""

    def __init__(self, message: str, status_code: int | None = None,
                 payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OzonClient:
    """Клиент для взаимодействия с OZON Seller API."""

    def __init__(self, config: OzonConfig, base_url: str = API_BASE_URL,
                 timeout: int = 30) -> None:
        self._config = config
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Client-Id": config.client_id,
                "Api-Key": config.api_key,
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str,
                 payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Выполнить запрос к API и вернуть JSON-ответ.

        Raises:
            OzonApiError: при сетевой ошибке или ошибке API.
        """
        url = f"{self._base_url}{path}"
        try:
            if payload is not None:
                response = self._session.request(
                    method, url, json=payload, timeout=self._timeout
                )
            else:
                response = self._session.request(method, url, timeout=self._timeout)
        except requests.RequestException as exc:
            raise OzonApiError(
                f"Сетевая ошибка при запросе {method} {path}: {exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError:
            data = None

        if response.status_code >= 400:
            message = self._extract_error_message(data, response.status_code)
            raise OzonApiError(
                f"OZON API вернул ошибку {response.status_code} для {path}: {message}",
                status_code=response.status_code,
                payload=data,
            )

        if not isinstance(data, dict):
            raise OzonApiError(
                f"Неожиданный формат ответа от {path}: {data!r}",
                status_code=response.status_code,
            )

        return data

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Выполнить POST-запрос к API."""
        return self._request("POST", path, payload)

    def _get(self, path: str) -> dict[str, Any]:
        """Выполнить GET-запрос к API."""
        return self._request("GET", path)

    @staticmethod
    def _extract_error_message(data: Any, status_code: int) -> str:
        """Извлечь человекочитаемое сообщение об ошибке из ответа API."""
        if isinstance(data, dict):
            message = data.get("message") or data.get("error")
            if message:
                return str(message)
            code = data.get("code")
            if code:
                return f"code={code}"
        return f"HTTP {status_code}"

    # ------------------------------------------------------------------
    # Методы для работы с промоакциями
    # ------------------------------------------------------------------

    def get_actions(self) -> list[dict[str, Any]]:
        """Получить список промоакций.

        Returns:
            Список акций (каждая — словарь с данными акции).
        """
        data = self._get("/v1/actions")
        return data.get("result", [])

    def get_auto_add_products(self, action_id: int,
                              auto_add_date: str) -> list[dict[str, Any]]:
        """Получить товары авто-добавления акции с учётом пагинации.

        Args:
            action_id: идентификатор акции.
            auto_add_date: дата авто-добавления (RFC3339).

        Returns:
            Список товаров акции (содержат ``min_seller_price``).
        """
        products: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            payload = {
                "action_id": action_id,
                "auto_add_date": auto_add_date,
                "limit": limit,
                "offset": offset,
            }
            data = self._post("/v2/actions/auto-add/products/list", payload)
            items = data.get("products", [])
            products.extend(items)

            offset += len(items)
            total = data.get("total")

            if not items or len(items) < limit:
                break
            if isinstance(total, int) and offset >= total:
                break

        return products

    def delete_action_products(self, action_id: int, auto_add_date: str,
                               product_ids: list[int]) -> dict[str, Any]:
        """Удалить товары из очереди авто-добавления акции.

        Args:
            action_id: идентификатор акции.
            auto_add_date: дата авто-добавления (RFC3339).
            product_ids: список идентификаторов товаров для удаления.

        Returns:
            Ответ API.
        """
        payload = {
            "action_id": action_id,
            "auto_add_date": auto_add_date,
            "product_ids": product_ids,
        }
        return self._post("/v2/actions/auto-add/products/delete", payload)

    def get_action_products(self, action_id: int) -> list[dict[str, Any]]:
        """Получить товары, уже участвующие в акции (с пагинацией).

        Returns:
            Список товаров с полями ``id``, ``price``, ``action_price`` и др.
        """
        products: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            payload = {
                "action_id": action_id,
                "limit": limit,
                "offset": offset,
            }
            data = self._post("/v1/actions/products", payload)
            result = data.get("result", {})
            items = result.get("products", [])
            products.extend(items)

            offset += len(items)
            total = result.get("total")

            if not items or len(items) < limit:
                break
            if isinstance(total, int) and offset >= total:
                break

        return products

    def get_product_price_info(self, product_ids: list[int]) -> dict[int, ProductPriceInfo]:
        """Получить минимальные цены и артикулы для списка товаров.

        Args:
            product_ids: идентификаторы товаров OZON.

        Returns:
            Словарь ``product_id -> ProductPriceInfo``.
        """
        if not product_ids:
            return {}

        info: dict[int, ProductPriceInfo] = {}
        batch_size = 100

        for start in range(0, len(product_ids), batch_size):
            batch = product_ids[start : start + batch_size]
            payload = {
                "filter": {
                    "product_id": [str(product_id) for product_id in batch],
                    "visibility": "ALL",
                },
                "limit": batch_size,
            }
            data = self._post("/v5/product/info/prices", payload)

            for item in data.get("items", []):
                product_id = item.get("product_id")
                if product_id is None:
                    continue

                price_block = item.get("price") or {}
                min_price_raw = price_block.get("min_price")
                if min_price_raw is None:
                    continue

                try:
                    min_price = float(min_price_raw)
                except (TypeError, ValueError):
                    continue

                offer_id = str(item.get("offer_id") or "")
                info[int(product_id)] = ProductPriceInfo(
                    min_price=min_price,
                    offer_id=offer_id,
                )

        return info

    def get_product_min_prices(self, product_ids: list[int]) -> dict[int, float]:
        """Получить минимальные цены продавца для списка товаров.

        Args:
            product_ids: идентификаторы товаров OZON.

        Returns:
            Словарь ``product_id -> min_price``.
        """
        return {
            product_id: item.min_price
            for product_id, item in self.get_product_price_info(product_ids).items()
        }

    def deactivate_action_products(self, action_id: int,
                                   product_ids: list[int]) -> dict[str, Any]:
        """Удалить товары из акции (уже участвующие).

        Args:
            action_id: идентификатор акции.
            product_ids: список идентификаторов товаров для удаления.

        Returns:
            Ответ API.
        """
        payload = {
            "action_id": action_id,
            "product_ids": product_ids,
        }
        return self._post("/v1/actions/products/deactivate", payload)
