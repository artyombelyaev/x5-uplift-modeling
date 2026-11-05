# Оценка на test за один запуск, по замороженному плану (docs/plan.md, «Заморозка перед test»).
# Запуск: python -m src.evaluate_test. Результат - artifacts/test_results.json, ноутбук 05 только читает его.

import json
import logging
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config, models, uplift

FINAL = "class_transformation"
COMPARED = ["t_learner", "response", "inverse_response"]
SCORED = [FINAL] + COMPARED
KS = (0.1, 0.2, 0.3)
SHARES = np.arange(0, 101) / 100
R_GRID = np.round(np.arange(0, 0.30001, 0.0025), 4)
N_BOOT = 1000
N_PERM = 1000
BOOT_SEED = 42
PER = 100_000
log = logging.getLogger("evaluate_test")


def load_models() -> dict:
    return {
        name: lgb.Booster(model_file=str(models.ARTIFACTS / "models" / f"{name}.txt"))
        for name in ("response", "t_treatment", "t_control", "class_transformation")
    }


def all_scores(boosters: dict, X) -> dict:
    s = models.score(boosters, X)
    s["inverse_response"] = -s["response"]
    return s


# Модели из файлов должны давать на valid ровно те скоры, что оценивались на этапе 4.
def check_valid(boosters: dict) -> dict:
    X_valid, y_valid, t_valid = models.load("valid")
    saved = pd.read_parquet(models.ARTIFACTS / "valid_scores.parquet").query(f"seed == {config.SEED}")
    saved = saved.pivot(index="client_id", columns="model", values="score").loc[X_valid.index]
    s = all_scores(boosters, X_valid)
    for m in ("response", "t_learner", "class_transformation"):
        assert np.allclose(s[m], saved[m].to_numpy()), m
    return {"scores": s, "y": y_valid, "t": t_valid}


def ci(a) -> list:
    return [float(v) for v in np.quantile(a, [0.025, 0.975])]


def main() -> None:
    models.ARTIFACTS.mkdir(exist_ok=True)
    logging.basicConfig(filename=models.ARTIFACTS / "evaluate_test.log", level=logging.INFO,
                        format="%(asctime)s %(message)s")
    start = time.time()
    boosters = load_models()
    valid = check_valid(boosters)
    log.info("valid scores match stage 4")

    X, y, t = models.load("test")
    scores = all_scores(boosters, X)
    log.info(f"test: {len(y)} clients, treatment {int(t.sum())}")

    # Доля рассылки для каждого r выбирается на valid, прибыль при ней оценивается на test.
    valid_gain = {m: uplift.gain_curve(valid["y"], valid["t"], valid["scores"][m], SHARES) for m in SCORED}
    chosen = {m: uplift.best_share(valid_gain[m], SHARES, R_GRID) for m in SCORED}
    chosen_idx = {m: np.searchsorted(SHARES, chosen[m]) for m in SCORED}

    ate = y[t == 1].mean() - y[t == 0].mean()
    point = {m: uplift.metrics(y, t, scores[m], KS) for m in SCORED}
    counts = {m: {f"{k:.0%}": uplift.uplift_at_k(y, t, scores[m], k)[1:] for k in KS} for m in SCORED}
    gain = {m: uplift.gain_curve(y, t, scores[m], SHARES) for m in SCORED}

    rng = np.random.default_rng(BOOT_SEED)
    idx_t, idx_c = np.where(t == 1)[0], np.where(t == 0)[0]
    boot = {"ate": [], **{m: {"metrics": [], "gain": []} for m in SCORED}}
    for b in range(N_BOOT):
        idx = np.r_[rng.choice(idx_t, idx_t.size), rng.choice(idx_c, idx_c.size)]
        yb, tb = y[idx], t[idx]
        boot["ate"].append(yb[tb == 1].mean() - yb[tb == 0].mean())
        for m in SCORED:
            sb = scores[m][idx]
            boot[m]["metrics"].append(uplift.metrics(yb, tb, sb, KS))
            boot[m]["gain"].append(uplift.gain_curve(yb, tb, sb, SHARES))
        if (b + 1) % 100 == 0:
            log.info(f"bootstrap {b + 1}/{N_BOOT}, {time.time() - start:.0f} s")
    boot_ate = np.array(boot["ate"])
    boot_metrics = {m: pd.DataFrame(boot[m]["metrics"]) for m in SCORED}
    boot_gain = {m: np.array(boot[m]["gain"]) for m in SCORED}

    rng = np.random.default_rng(BOOT_SEED)
    perm_metrics, perm_gain = [], []
    for _ in range(N_PERM):
        s = rng.permutation(len(y))
        perm_metrics.append(uplift.metrics(y, t, s, KS))
        perm_gain.append(uplift.gain_curve(y, t, s, SHARES))
    perm_metrics, perm_gain = pd.DataFrame(perm_metrics), np.array(perm_gain)
    log.info(f"permutations done, {time.time() - start:.0f} s")

    metric_names = ["qini", "qini_area"] + [f"uplift@{k:.0%}" for k in KS]
    res = {
        "n": int(len(y)), "n_treatment": int(t.sum()), "n_control": int((1 - t).sum()),
        "ate": float(ate), "ate_ci": ci(boot_ate),
        "ks": list(KS), "shares": SHARES.tolist(), "r_grid": R_GRID.tolist(),
        "n_boot": N_BOOT, "n_perm": N_PERM, "boot_seed": BOOT_SEED,
        "models": {},
        "random": {
            "metrics_ci": {c: ci(perm_metrics[c]) for c in metric_names},
            "gain_band": [np.quantile(perm_gain, q, axis=0).tolist() for q in (0.025, 0.975)],
        },
        "differences": {},
        "economics": {},
    }
    for m in SCORED:
        res["models"][m] = {
            "metrics": {c: float(point[m][c]) for c in metric_names},
            "metrics_ci": {c: ci(boot_metrics[m][c]) for c in metric_names},
            "counts": {k: [int(v) for v in c] for k, c in counts[m].items()},
            "gain": gain[m].tolist(),
            "gain_ci": [np.quantile(boot_gain[m], q, axis=0).tolist() for q in (0.025, 0.975)],
        }

    # Парные разности на одних и тех же бутстреп-выборках: финальная минус каждый бейзлайн и T-learner.
    for m in COMPARED:
        d = boot_metrics[FINAL][metric_names] - boot_metrics[m][metric_names]
        res["differences"][f"{FINAL} - {m}"] = {
            c: {"estimate": float(point[FINAL][c] - point[m][c]), "ci": ci(d[c])} for c in metric_names
        }
    res["differences"][f"{FINAL} - random"] = {
        **{c: {"estimate": float(point[FINAL][c] - ate), "ci": ci(boot_metrics[FINAL][c] - boot_ate)}
           for c in metric_names[2:]},
        "qini": {"estimate": float(point[FINAL]["qini"]), "ci": ci(boot_metrics[FINAL]["qini"])},
    }

    # Экономика в единицах V на 100 000 клиентов: прибыль = доп. покупатели - r * отправлено.
    send_all = PER * (ate - R_GRID)
    send_all_boot = PER * (boot_ate[:, None] - R_GRID[None, :])
    profit, profit_boot = {}, {}
    for m in SCORED:
        k = chosen[m]
        profit[m] = PER * (gain[m][chosen_idx[m]] - R_GRID * k)
        profit_boot[m] = PER * (boot_gain[m][:, chosen_idx[m]] - R_GRID[None, :] * k[None, :])
        res["economics"][m] = {
            "share_chosen_on_valid": k.tolist(),
            "profit": profit[m].tolist(),
            "profit_ci": [np.quantile(profit_boot[m], q, axis=0).tolist() for q in (0.025, 0.975)],
        }
    res["economics"]["send_all"] = {
        "profit": send_all.tolist(),
        "profit_ci": [np.quantile(send_all_boot, q, axis=0).tolist() for q in (0.025, 0.975)],
    }
    for name, other, other_boot in [("send_all", send_all, send_all_boot),
                                    ("inverse_response", profit["inverse_response"], profit_boot["inverse_response"])]:
        d = profit_boot[FINAL] - other_boot
        res["economics"][f"gain_vs_{name}"] = {
            "estimate": (profit[FINAL] - other).tolist(),
            "ci": [np.quantile(d, q, axis=0).tolist() for q in (0.025, 0.975)],
        }

    (models.ARTIFACTS / "test_results.json").write_text(json.dumps(res, indent=1))
    log.info(f"done, {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
