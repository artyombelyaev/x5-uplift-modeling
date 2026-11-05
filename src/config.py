# Пути и общие константы.

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Датасет лежит в data/ или в папке из X5_DATA_DIR.
DATA_DIR = Path(os.environ.get("X5_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
TRAIN_CSV = RAW_DIR / "uplift_train.csv.gz"
CLIENTS_CSV = RAW_DIR / "clients.csv.gz"
PURCHASES_CSV = RAW_DIR / "purchases.csv.gz"
PURCHASES_PARQUET = DATA_DIR / "purchases.parquet"
SPLIT_PARQUET = DATA_DIR / "split.parquet"
FEATURES_PARQUET = DATA_DIR / "features.parquet"
FEATURES_ALL_PARQUET = DATA_DIR / "features_all.parquet"
SCORES_PARQUET = DATA_DIR / "scores_raw.parquet"
SEND_SHARES_PARQUET = DATA_DIR / "send_shares.parquet"
SCORES_MART_PARQUET = DATA_DIR / "scores.parquet"
SQL_DIR = ROOT / "sql"

SEED = 42
SPLIT_SHARES = {"train": 0.6, "valid": 0.2, "test": 0.2}

# Последний день истории, который считаем «до коммуникации». Пока это последний день в purchases;
# может сдвинуться раньше после проверки на этапе 2.
CUTOFF = date(2019, 3, 18)

# Даты в clients на столько часов позже, чем в purchases (этап 1). В staging.sql они сдвигаются назад.
CLIENTS_TZ_SHIFT = 3

# Возраст вне [AGE_MIN, AGE_MAX] считаю ошибкой и заменяю на NULL.
AGE_MIN = 14
AGE_MAX = 100

# r = C / V для флага send в витрине скоров (допущение, меняется параметром запроса).
R_DEFAULT = 0.05
