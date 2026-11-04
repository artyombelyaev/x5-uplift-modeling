# Uplift-моделирование на X5 RetailHero

X5 провела рандомизированную коммуникацию с клиентами: половине отправили, половине нет, и отметили, была ли
после этого покупка. Я разбираю эксперимент как аналитик: работает ли коммуникация в среднем, у кого она меняет
решение о покупке и сколько дополнительных покупателей даёт рассылка по uplift-модели на 1 000 сообщений
по сравнению со случайной рассылкой и с рассылкой по модели отклика.

План анализа - метрики, бейзлайны, правило выбора модели и однократная оценка на test - записан в
[docs/plan.md](docs/plan.md) до обучения моделей.

## Как устроено решение

1. Проверка данных. Все агрегаты и проверки написаны на SQL и выполняются в DuckDB. Размеры таблиц и доли сходятся
   с описанием датасета: 200 039 клиентов в эксперименте, target 0,62, treatment 0,50. Дублей нет, все клиенты
   эксперимента есть в истории покупок. `transaction_id` уникален только в паре с `client_id`: 28 значений
   встречаются у двух разных клиентов, поэтому чек - это пара. Даты в `clients` на 3 часа позже, чем в purchases:
   `first_redeem_date` ровно на 3 часа позже первого списания баллов у 97,2% клиентов. После сдвига списаний раньше
   неё нет ни у кого, так что колонка - это первое списание, но в другом часовом поясе (предположение). Возраст вне
   14-100 лет у 1 779 клиентов, в витрине он будет NULL. Дату коммуникации и окно target по данным не установить:
   история обрывается на полном дне 2019-03-18, а `first_redeem_date` доходит до 2019-11-20, то есть `clients`
   содержит события после коммуникации.

## Как запустить

Нужен Python 3.13, на macOS ещё `brew install libomp` для LightGBM.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Скачать данные (около 680 МБ) и перевести purchases в parquet, несколько минут:

```bash
.venv/bin/python -m src.data
```

Разбиение train/valid/test, несколько секунд:

```bash
.venv/bin/python -m src.split
```

Ноутбук этапа 1, около 2,5 минут:

```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_quality.ipynb
```

Тесты:

```bash
.venv/bin/python -m pytest tests
```

## Структура

- `docs/plan.md` - план анализа, зафиксированный до обучения моделей.
- `sql/staging.sql` - вьюхи над исходными файлами.
- `sql/quality.sql` - ключи, дубли, пропуски, суммы чеков, возраст, даты и сдвиг на 3 часа.
- `src/config.py` - пути, сид, доли разбиения, `CUTOFF` и границы возраста.
- `src/db.py` - подключение к DuckDB и запуск именованных запросов из `sql/`.
- `src/data.py` - скачивание данных и перевод purchases в parquet.
- `src/split.py` - разбиение со стратификацией по treatment x target в `data/split.parquet`.
- `src/plots.py` - общее оформление графиков: цвета групп, белый фон, сохранение в `images/`.
- `tests/test_split.py` - доли разбиения, стратификация и воспроизводимость.
- `notebooks/01_data_quality.ipynb` - таблица колонок и отчёт о качестве данных.

## Ограничения

- В соревновании были ещё `products.csv` (справочник товаров) и `uplift_test.csv` (клиенты без target), но в источнике
  scikit-uplift их нет. Без справочника признаки по категориям товаров не строю.

## Данные и библиотеки

Датасет X5 RetailHero Uplift Modeling (X5 Retail Group, хакатон 2019,
https://ods.ai/competitions/x5-retailhero-uplift-modeling). Файлы скачиваются по ссылкам из `sklift.datasets.fetch_x5`.
Данные в репозиторий не входят.

- [DuckDB](https://duckdb.org) - MIT
- [pandas](https://pandas.pydata.org), [NumPy](https://numpy.org), [SciPy](https://scipy.org), [scikit-learn](https://scikit-learn.org) - BSD-3-Clause
- [PyArrow](https://arrow.apache.org) - Apache-2.0
- [LightGBM](https://github.com/microsoft/LightGBM) - MIT
- [scikit-uplift](https://github.com/maks-sh/scikit-uplift) - MIT, только для сверки метрик
- [Matplotlib](https://matplotlib.org) - Matplotlib License (на основе PSF)
- [Jupyter](https://jupyter.org) - BSD-3-Clause
- [pytest](https://pytest.org) - MIT
