# Витрина признаков из sql/features.sql.
# Запуск: python -m src.features - клиенты эксперимента в data/features.parquet (для моделей)
# и все клиенты clients в data/features_all.parquet (для витрины скоров). Логика одна и та же.

from . import config, db

POPULATIONS = {
    "experiment": ("select client_id from uplift_train", config.FEATURES_PARQUET),
    "all": ("select client_id from clients", config.FEATURES_ALL_PARQUET),
}


def build(population: str = "experiment") -> None:
    clients, path = POPULATIONS[population]
    con = db.connect()
    con.execute(f"create or replace temp view population as {clients}")
    query = db.queries("features.sql")["features"].rstrip(";")
    con.execute(f"copy ({query}) to '{path}' (format parquet)")


if __name__ == "__main__":
    for name in POPULATIONS:
        build(name)
