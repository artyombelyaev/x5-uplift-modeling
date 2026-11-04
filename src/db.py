# DuckDB в памяти: вьюхи из staging.sql и именованные запросы из sql/.

import re

import duckdb
import pandas as pd

from . import config


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name, value in {
        "train_csv": config.TRAIN_CSV,
        "clients_csv": config.CLIENTS_CSV,
        "purchases_parquet": config.PURCHASES_PARQUET,
        "split_parquet": config.SPLIT_PARQUET,
    }.items():
        con.execute(f"set variable {name} = '{value}'")
    con.execute(f"set variable cutoff = date '{config.CUTOFF}'")
    con.execute(f"set variable age_min = {config.AGE_MIN}")
    con.execute(f"set variable age_max = {config.AGE_MAX}")
    con.execute(read("staging.sql"))
    return con


def read(name: str) -> str:
    return (config.SQL_DIR / name).read_text()


# В одном файле несколько запросов, каждый начинается со строки "-- name: <имя>".
def queries(name: str) -> dict[str, str]:
    parts = re.split(r"^-- name: (\w+)[ \t]*$", read(name), flags=re.M)
    return {key: body.strip() for key, body in zip(parts[1::2], parts[2::2])}


def run(con: duckdb.DuckDBPyConnection, name: str, query: str) -> pd.DataFrame:
    return con.execute(queries(name)[query]).df()
