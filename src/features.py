# Витрина признаков из sql/features.sql в data/features.parquet.
# Запуск: python -m src.features

from . import config, db


def build() -> None:
    con = db.connect()
    query = db.queries("features.sql")["features"].rstrip(";")
    con.execute(f"copy ({query}) to '{config.FEATURES_PARQUET}' (format parquet)")


if __name__ == "__main__":
    build()
