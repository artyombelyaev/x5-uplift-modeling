# Метрики uplift: Qini-кривая, Qini-коэффициент, площадь между кривой и случайной линией, uplift@k, бутстреп.
# Определения те же, что в scikit-uplift 0.5.1 (qini_curve, qini_auc_score с negative_effect=True, uplift_at_k
# со strategy="overall"), сверка - в tests/test_uplift.py.

import numpy as np
import pandas as pd


# Клиенты по убыванию скора. Для первых n: Q(n) = Y_T(n) - Y_C(n) * N_T(n) / N_C(n).
# Точки только на границах разных значений скора: клиенты с одинаковым скором входят вместе.
def qini_curve(y, t, score):
    y, t, score = np.asarray(y), np.asarray(t), np.asarray(score)
    order = np.argsort(score, kind="mergesort")[::-1]
    y, t, score = y[order], t[order], score[order]
    ends = np.r_[np.where(np.diff(score))[0], score.size - 1]
    n_t = np.cumsum(t)[ends]
    y_t = np.cumsum(y * t)[ends]
    y_c = np.cumsum(y * (1 - t))[ends]
    n = ends + 1
    n_c = n - n_t
    ratio = np.divide(n_t, n_c, out=np.zeros(n_t.shape, dtype=float), where=n_c != 0)
    return np.r_[0, n], np.r_[0.0, y_t - y_c * ratio]


# Идеальная кривая с учётом отрицательного эффекта: сначала купившие в treatment, в конце - купившие в control.
def perfect_qini_curve(y, t):
    y, t = np.asarray(y), np.asarray(t)
    return qini_curve(y, t, y * t - y * (1 - t))


def _area_above_random(x, q):
    return np.trapezoid(q, x) - x[-1] * q[-1] / 2


def qini_coef(y, t, score):
    x, q = qini_curve(y, t, score)
    xp, qp = perfect_qini_curve(y, t)
    return _area_above_random(x, q) / _area_above_random(xp, qp)


# Площадь между кривой модели и случайной линией, делённая на число клиентов: средний зазор, в покупателях.
def qini_area(y, t, score):
    x, q = qini_curve(y, t, score)
    return _area_above_random(x, q) / x[-1]


# strategy="overall": топ-k всех клиентов по скору, внутри - разница долей покупателей treatment и control.
def uplift_at_k(y, t, score, k):
    y, t, score = np.asarray(y), np.asarray(t), np.asarray(score)
    top = np.argsort(score, kind="mergesort")[::-1][: int(len(y) * k)]
    y_top, t_top = y[top], t[top]
    n_t, n_c = int(t_top.sum()), int((1 - t_top).sum())
    return y_top[t_top == 1].mean() - y_top[t_top == 0].mean(), n_t, n_c


def metrics(y, t, score, ks=(0.1, 0.2, 0.3)) -> dict:
    out = {"qini": qini_coef(y, t, score), "qini_area": qini_area(y, t, score)}
    for k in ks:
        out[f"uplift@{k:.0%}"] = uplift_at_k(y, t, score, k)[0]
    return out


# Парный бутстреп: скоры фиксированы, клиентов пересэмплирую с возвращением отдельно внутри treatment и control,
# все модели считаются на одной и той же выборке. Возвращает таблицу повтор x модель x метрика.
def bootstrap(y, t, scores: dict, n_boot: int = 1000, seed: int = 42, ks=(0.1, 0.2, 0.3)) -> pd.DataFrame:
    y, t = np.asarray(y), np.asarray(t)
    rng = np.random.default_rng(seed)
    idx_t, idx_c = np.where(t == 1)[0], np.where(t == 0)[0]
    rows = []
    for b in range(n_boot):
        idx = np.r_[rng.choice(idx_t, idx_t.size), rng.choice(idx_c, idx_c.size)]
        yb, tb = y[idx], t[idx]
        rows.append({"rep": b, "model": "ate", "ate": yb[tb == 1].mean() - yb[tb == 0].mean()})
        for name, score in scores.items():
            rows.append({"rep": b, "model": name, **metrics(yb, tb, np.asarray(score)[idx], ks)})
    return pd.DataFrame(rows)


# Случайная рассылка: скоры случайно переставляются, распределение метрик показывает шум случайного таргетинга.
def permutation_baseline(y, t, n_perm: int = 1000, seed: int = 42, ks=(0.1, 0.2, 0.3)) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame([metrics(y, t, rng.permutation(len(y)), ks) for _ in range(n_perm)])
