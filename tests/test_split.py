import numpy as np
import pandas as pd

from src.split import split

SHARES = {"train": 0.6, "valid": 0.2, "test": 0.2}


def toy(n=10_000, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"treatment_flg": rng.integers(0, 2, n), "target": rng.random(n) < 0.6})


def test_shares_and_strata():
    clients = toy()
    part = split(clients, SHARES, seed=1)
    assert part.value_counts(normalize=True).round(3).to_dict() == SHARES
    cell = clients.treatment_flg.astype(str) + clients.target.astype(str)
    by_part = pd.crosstab(part, cell, normalize="index")
    overall = cell.value_counts(normalize=True)
    assert (by_part - overall).abs().max().max() < 0.002


def test_seed_is_fixed():
    clients = toy()
    assert split(clients, SHARES, seed=1).equals(split(clients, SHARES, seed=1))
