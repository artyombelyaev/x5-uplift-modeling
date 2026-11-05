# Модель отклика, T-learner и трансформация классов на LightGBM. Гиперпараметры - 5-fold CV внутри train.
# Запуск: python -m src.models. Результаты в artifacts/: таблица CV, модели seed 42, скоры на valid для 5 seed.
# test здесь не используется.

import json
import logging
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from . import config, db

ARTIFACTS = config.ROOT / "artifacts"
SEEDS = [42, 43, 44, 45, 46]
log = logging.getLogger("train")

FIXED = {
    "objective": "binary",
    "metric": "binary_logloss",
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "num_threads": 4,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}
GRID = [
    {"num_leaves": nl, "min_child_samples": mcs, "learning_rate": lr}
    for nl in (15, 31, 63)
    for mcs in (100, 400, 1600)
    for lr in (0.03, 0.1)
]


def load(part: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    con = db.connect()
    df = con.execute(f"""
        select f.*, u.treatment_flg, u.target
        from read_parquet(getvariable('features_parquet')) f
        join uplift_train u using (client_id)
        join read_parquet(getvariable('split_parquet')) s using (client_id)
        where s.part = '{part}'
        order by client_id
    """).df()
    X = df.drop(columns=["treatment_flg", "target"]).set_index("client_id")
    X["gender"] = X.gender.astype(pd.CategoricalDtype(["F", "M", "U"]))
    return X, df.target.to_numpy(), df.treatment_flg.to_numpy()


# Ранняя остановка на отложенном фолде. Критерий - средний logloss в лучших итерациях,
# число деревьев финальной модели - медиана лучших итераций по фолдам.
def cv_search(X, y, strata, name: str, seed: int = config.SEED) -> pd.DataFrame:
    folds = list(StratifiedKFold(5, shuffle=True, random_state=seed).split(X, strata))
    rows = []
    for i, params in enumerate(GRID, 1):
        iters, losses = [], []
        for f, (fit_idx, val_idx) in enumerate(folds, 1):
            start = time.time()
            m = lgb.train(
                {**FIXED, **params, "seed": seed},
                lgb.Dataset(X.iloc[fit_idx], y[fit_idx]),
                num_boost_round=3000,
                valid_sets=[lgb.Dataset(X.iloc[val_idx], y[val_idx])],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )
            iters.append(m.best_iteration)
            losses.append(m.best_score["valid_0"]["binary_logloss"])
            log.info(f"{name} {i}/{len(GRID)} {params} fold {f}: iter {m.best_iteration}, "
                     f"logloss {losses[-1]:.5f}, {time.time() - start:.1f} s")
        rows.append({**params, "n_trees": int(np.median(iters)), "cv_logloss": float(np.mean(losses)),
                     "fold_iters": iters})
    return pd.DataFrame(rows).sort_values("cv_logloss").reset_index(drop=True)


def fit(X, y, best: dict, seed: int) -> lgb.Booster:
    params = {
        "num_leaves": int(best["num_leaves"]),
        "min_child_samples": int(best["min_child_samples"]),
        "learning_rate": float(best["learning_rate"]),
    }
    return lgb.train({**FIXED, **params, "seed": seed}, lgb.Dataset(X, y), num_boost_round=int(best["n_trees"]))


# Z = 1 у купивших в treatment и не купивших в control. При доле treatment 0,5 uplift = 2 * P(Z = 1) - 1.
def class_target(y, t):
    return y * t + (1 - y) * (1 - t)


def score(models: dict, X) -> dict:
    return {
        "response": models["response"].predict(X),
        "t_learner": models["t_treatment"].predict(X) - models["t_control"].predict(X),
        "class_transformation": 2 * models["class_transformation"].predict(X) - 1,
    }


def train_all(X, y, t, best: dict, seed: int) -> dict:
    tr, ct = t == 1, t == 0
    return {
        "response": fit(X[tr], y[tr], best["response"], seed),
        "t_treatment": fit(X[tr], y[tr], best["t_treatment"], seed),
        "t_control": fit(X[ct], y[ct], best["t_control"], seed),
        "class_transformation": fit(X, class_target(y, t), best["class_transformation"], seed),
    }


if __name__ == "__main__":
    ARTIFACTS.mkdir(exist_ok=True)
    logging.basicConfig(filename=ARTIFACTS / "train.log", level=logging.INFO, format="%(asctime)s %(message)s")
    X, y, t = load("train")
    tr, ct = t == 1, t == 0
    z = class_target(y, t)
    log.info(f"train: {len(y)} clients, treatment share {t.mean():.4f}")
    # Модель отклика и treatment-модель T-learner учатся на одних данных, поэтому поиск у них общий.
    searches = {
        "response": cv_search(X[tr], y[tr], y[tr], "response"),
        "t_control": cv_search(X[ct], y[ct], y[ct], "t_control"),
        "class_transformation": cv_search(X, z, 2 * t + y, "class_transformation"),
    }
    searches["t_treatment"] = searches["response"]
    pd.concat([s.assign(model=m) for m, s in searches.items() if m != "t_treatment"]).to_csv(
        ARTIFACTS / "cv_results.csv", index=False
    )
    best = {m: s.drop(columns="fold_iters").iloc[0].to_dict() for m, s in searches.items()}
    (ARTIFACTS / "best_params.json").write_text(json.dumps(best, indent=2))

    X_valid, _, _ = load("valid")
    scores = []
    for seed in SEEDS:
        start = time.time()
        models = train_all(X, y, t, best, seed)
        log.info(f"final fit seed {seed}: {time.time() - start:.1f} s")
        if seed == config.SEED:
            (ARTIFACTS / "models").mkdir(exist_ok=True)
            for name, m in models.items():
                m.save_model(ARTIFACTS / "models" / f"{name}.txt")
        for name, s in score(models, X_valid).items():
            scores.append(pd.DataFrame({"client_id": X_valid.index, "model": name, "seed": seed, "score": s}))
    pd.concat(scores).to_parquet(ARTIFACTS / "valid_scores.parquet", index=False)
    log.info("done")
