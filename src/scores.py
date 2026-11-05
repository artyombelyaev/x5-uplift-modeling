# Скоры финальной модели и модели отклика для всех клиентов clients и доли рассылки по r, выбранные на valid.
# Запуск: python -m src.scores (после src.features и src.models). Витрина поверх них - sql/scores.sql.

import numpy as np
import pandas as pd

from . import config, db, evaluate_test, models, uplift


def score_all() -> pd.DataFrame:
    X = pd.read_parquet(config.FEATURES_ALL_PARQUET).set_index("client_id")
    X["gender"] = X.gender.astype(pd.CategoricalDtype(["F", "M", "U"]))
    s = evaluate_test.all_scores(evaluate_test.load_models(), X)
    return pd.DataFrame({"client_id": X.index, "uplift_score": s[evaluate_test.FINAL], "p_t": s["response"]})


# Та же процедура, что в экономике этапа 5: для каждого r доля k с наибольшей прибылью на valid.
def send_shares() -> pd.DataFrame:
    X, y, t = models.load("valid")
    saved = pd.read_parquet(models.ARTIFACTS / "valid_scores.parquet").query(f"seed == {config.SEED}")
    score = saved.pivot(index="client_id", columns="model", values="score").loc[X.index, evaluate_test.FINAL]
    gain = uplift.gain_curve(y, t, score.to_numpy(), evaluate_test.SHARES)
    k = uplift.best_share(gain, evaluate_test.SHARES, evaluate_test.R_GRID)
    return pd.DataFrame({"r": evaluate_test.R_GRID, "k": k})


def build() -> None:
    score_all().to_parquet(config.SCORES_PARQUET, index=False)
    send_shares().to_parquet(config.SEND_SHARES_PARQUET, index=False)
    con = db.connect()
    query = db.queries("scores.sql")["scores"].rstrip(";")
    con.execute(f"copy ({query}) to '{config.SCORES_MART_PARQUET}' (format parquet)")


if __name__ == "__main__":
    build()
