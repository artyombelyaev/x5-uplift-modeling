# SRM, SMD, интервалы для разницы долей и бутстреп.

import numpy as np
from scipy import stats


def srm(n_treatment: int, n_control: int, share: float = 0.5) -> tuple[float, float]:
    n = n_treatment + n_control
    res = stats.chisquare([n_treatment, n_control], [n * share, n * (1 - share)])
    return float(res.statistic), float(res.pvalue)


# Стандартизованная разница средних: делю на корень из средней дисперсии двух групп.
def smd(mean_t, mean_c, var_t, var_c):
    return (mean_t - mean_c) / np.sqrt((var_t + var_c) / 2)


def prop_ci(k, n, alpha: float = 0.05):
    p = np.asarray(k) / np.asarray(n)
    z = stats.norm.ppf(1 - alpha / 2)
    se = np.sqrt(p * (1 - p) / n)
    return p, p - z * se, p + z * se


def diff_props_ci(k_t, n_t, k_c, n_c, alpha: float = 0.05):
    p_t, p_c = np.asarray(k_t) / n_t, np.asarray(k_c) / n_c
    z = stats.norm.ppf(1 - alpha / 2)
    se = np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    d = p_t - p_c
    return d, d - z * se, d + z * se


def diff_means_ci(mean_t, var_t, n_t, mean_c, var_c, n_c, alpha: float = 0.05):
    z = stats.norm.ppf(1 - alpha / 2)
    se = np.sqrt(np.asarray(var_t) / n_t + np.asarray(var_c) / n_c)
    d = np.asarray(mean_t) - np.asarray(mean_c)
    return d, d - z * se, d + z * se


# Бутстреп разницы средних: клиентов пересэмплирую с возвращением отдельно внутри treatment и control.
def bootstrap_diff(y_t, y_c, n_boot: int = 1000, seed: int = 42, alpha: float = 0.05):
    rng = np.random.default_rng(seed)
    y_t, y_c = np.asarray(y_t, dtype=float), np.asarray(y_c, dtype=float)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = rng.choice(y_t, y_t.size).mean() - rng.choice(y_c, y_c.size).mean()
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return y_t.mean() - y_c.mean(), lo, hi
