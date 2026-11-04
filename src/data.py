# Скачивает три файла X5 RetailHero по ссылкам из sklift.datasets.fetch_x5 и переводит purchases в parquet.
# Запуск: python -m src.data

import shutil
import urllib.request

import duckdb

from . import config

URL = "https://sklift.s3.eu-west-2.amazonaws.com/{}"


def download(path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(URL.format(path.name)) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.rename(path)


# 45,8 млн строк из gz читаются около 35 секунд, из parquet - в разы быстрее.
def to_parquet() -> None:
    if config.PURCHASES_PARQUET.exists():
        return
    con = duckdb.connect()
    con.execute(f"""
        copy (select * from read_csv('{config.PURCHASES_CSV}'))
        to '{config.PURCHASES_PARQUET}' (format parquet, compression zstd)
    """)


if __name__ == "__main__":
    for p in (config.TRAIN_CSV, config.CLIENTS_CSV, config.PURCHASES_CSV):
        download(p)
    to_parquet()
