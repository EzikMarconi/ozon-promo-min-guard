# Ozon Promo Min Guard

Консольная программа на Python для поиска и удаления товаров в **акциях OZON**,
продающихся **ниже минимальной цены** — через [OZON Seller API](https://docs.ozon.ru/api/seller/).

Программа:
1. Получает список промоакций.
2. Для **каждой** акции получает участвующие товары и сравнивает
   «цену по акции» с минимальной ценой продавца (как в интерфейсе OZON).
3. Дополнительно проверяет очередь **авто-добавления** (товары, которые
   ещё не в акции, но будут добавлены по заниженной цене).
4. Сохраняет отчёт о найденных товарах в JSON и CSV файлы.
5. Позволяет удалить найденные товары из акции.

## Требования

- Python 3.9+
- Установленная библиотека `requests`

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

1. Скопируйте шаблон конфигурации:

```bash
# Linux / macOS / Git Bash
cp config.example.json config.json

# Windows (PowerShell / cmd)
copy config.example.json config.json
```

2. Укажите свои креды OZON Seller API в `config.json`:

```json
{
  "Ozon": {
    "ApiKey": "ваш-api-key",
    "ClientId": "ваш-client-id"
  }
}
```

Файл `config.json` добавлен в `.gitignore` и **не попадает в git**.
При необходимости можно указать другой файл конфигурации через аргумент `--config`.

## Использование

### 1. Проверка акций и формирование отчёта

```bash
python main.py check
```

Команда:
- получает список акций;
- для каждой акции получает **участвующие** товары и сравнивает
  `action_price` с `min_price` из каталога;
- дополнительно проверяет очередь авто-добавления
  (`action_price_to_auto_add` vs `min_seller_price`);
- выводит в консоль таблицу найденных товаров;
- сохраняет отчёт в `report.json` и `report.csv`.

Дополнительные параметры:

```bash
# Указать свои пути к отчётам
python main.py check --json my_report.json --csv my_report.csv

# Не сохранять CSV-отчёт
python main.py check --no-csv

# Указать другой файл конфигурации
python main.py check --config my_config.json
```

### 2. Удаление товаров из акции

Команда читает отчёт (JSON или CSV), созданный командой `check`, и удаляет
указанные товары из соответствующих акций.

```bash
python main.py delete report.json
```

По умолчанию программа запросит подтверждение перед удалением. Чтобы удалить
без запроса, добавьте флаг `--yes`:

```bash
python main.py delete report.json --yes
```

## Структура проекта

```
ozon-promo-min-guard/
├── config.example.json    # Шаблон конфигурации (копировать в config.json)
├── config.json            # Локальные креды (не в git)
├── requirements.txt       # Зависимости
├── README.md              # Эта инструкция
├── main.py                # Точка входа
└── ozon_promo_min_guard/
    ├── __init__.py
    ├── config.py          # Загрузка и валидация конфига
    ├── client.py          # HTTP-клиент для OZON API
    ├── actions.py         # Логика работы с акциями
    ├── report.py          # Формирование и чтение отчёта
    └── cli.py             # CLI-интерфейс
```

## Используемые эндпоинты API

| Назначение | Метод и путь |
|---|---|
| Список акций | `GET /v1/actions` |
| Участвующие товары в акции | `POST /v1/actions/products` |
| Минимальные цены товаров | `POST /v5/product/info/prices` |
| Товары авто-добавления в акции | `POST /v1/actions/auto-add/products/list` |
| Удаление участвующих товаров | `POST /v1/actions/products/deactivate` |
| Удаление из очереди авто-добавления | `POST /v1/actions/auto-add/products/delete` |

## Логика сравнения цен

### Участвующие товары (основной источник, совпадает с UI)

Для каждого товара в акции сравниваются:

- **`action_price`** из `/v1/actions/products` — «Цена по этой акции»;
- **`min_price`** из `/v5/product/info/prices` — «Минимальная цена».

Товар попадает в отчёт, если `action_price < min_price`.

### Очередь авто-добавления (дополнительно)

- **`action_price_to_auto_add`** — цена при будущем авто-добавлении;
- **`min_seller_price`** — минимальная цена из ответа auto-add API.

Товар попадает в отчёт, если `action_price_to_auto_add < min_seller_price`.

## Формат отчёта

Каждая запись отчёта содержит:

| Поле | Описание |
|---|---|
| `action_id` | ID акции |
| `action_title` | Название акции |
| `product_id` | ID товара |
| `offer_id` | Артикул продавца |
| `price` | Цена товара в акции (`action_price_to_auto_add`) |
| `min_seller_price` | Минимальная цена продавца |
| `difference` | Насколько цена ниже минимальной |
| `source` | `participating` (в акции) или `auto_add` (очередь авто-добавления) |
| `auto_add_date` | Дата авто-добавления (только для `auto_add`, используется при удалении) |
