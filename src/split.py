# Разбиение клиентов uplift_train на train/valid/test со стратификацией по treatment_flg x target.
# Запуск: python -m src.split. Результат в data/split.parquet (client_id, part).

import pandas as pd
from sklearn.model_selection import train_test_split

from . import config, db


def split(clients: pd.DataFrame, shares: dict[str, float], seed: int) -> pd.Series:
    strata = clients.treatment_flg.astype(str) + clients.target.astype(str)
    rest, test = train_test_split(clients.index, test_size=shares["test"], stratify=strata, random_state=seed)
    valid_size = shares["valid"] / (shares["train"] + shares["valid"])
    train, valid = train_test_split(rest, test_size=valid_size, stratify=strata[rest], random_state=seed)
    part = pd.Series("train", index=clients.index)
    part[valid] = "valid"
    part[test] = "test"
    return part


if __name__ == "__main__":
    con = db.connect()
    clients = con.execute("select client_id, treatment_flg, target from uplift_train order by client_id").df()
    clients["part"] = split(clients, config.SPLIT_SHARES, config.SEED)
    clients[["client_id", "part"]].to_parquet(config.SPLIT_PARQUET, index=False)
