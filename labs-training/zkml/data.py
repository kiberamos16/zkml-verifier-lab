"""The UCI credit-default dataset, as Lab 05's circuit needs it.

Doc 21 §11: 30,000 rows, CC BY 4.0, eight standardised features. The dataset is
downloaded once from the UCI archive, checked against a pinned SHA-256 before
it is parsed, and cached -- the same treatment every model file in this repo
gets, for the same reason: a file that changed under a fixed reference is a
supply-chain event, not a surprise to shrug at.

**Which eight features, and why it is not an arbitrary choice.**

The dataset carries 23. Four of them -- ``SEX``, ``EDUCATION``, ``MARRIAGE``
and ``AGE`` -- are protected or quasi-protected attributes. A credit-risk model
that keys on them is a fairness problem in any jurisdiction, and this one is
going on a public portfolio page where a visitor can type their own numbers
into it. They are excluded deliberately, not overlooked, and the model card
says so.

What is left is behaviour: how much credit the account has, how late its recent
payments have run, what it was last billed, and what it actually paid. Those
eight are also where this dataset's predictive signal genuinely lives --
``PAY_0`` alone carries more of it than every demographic column together --
so the exclusion costs very little AUC, and the model card reports what it
costs rather than asserting it is free.
"""

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SOURCE_URL = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"

# Observed on 2026-10-14 by downloading it. Checked before every parse.
SOURCE_SHA256 = "56c885f84457f6680f8438f02bfcdac9579323d8a94465ee5f26e32baa727602"

MEMBER = "default of credit card clients.xls"

# The eight the circuit sees, in the order it sees them. The order is part of
# the interface: the browser builds a witness from a form and the circuit
# indexes positionally, so reordering this list silently changes what every
# committed proof means.
FEATURES = (
    "LIMIT_BAL",
    "PAY_0",
    "PAY_2",
    "PAY_3",
    "PAY_4",
    "BILL_AMT1",
    "PAY_AMT1",
    "PAY_AMT2",
)

# Present in the file and deliberately unused. Named so that a later reader can
# see the decision was made rather than wonder whether the columns were missed.
EXCLUDED_PROTECTED = ("SEX", "EDUCATION", "MARRIAGE", "AGE")

TARGET = "default payment next month"


@dataclass(frozen=True)
class Dataset:
    """Standardised features and binary labels, already split.

    The standardisation statistics come from the training rows only. Computing
    them over everything is the most common way to leak a test set, and it
    inflates exactly the number this lab prints on screen.
    """

    x_train: np.ndarray
    y_train: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    raw_test: np.ndarray
    """Unstandardised test features, so the lab can prefill its form with a real row."""


def download(cache: Path) -> bytes:
    """Fetches the archive, verifying the hash before anything parses it."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file():
        blob = cache.read_bytes()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
            blob = response.read()
        cache.write_bytes(blob)

    digest = hashlib.sha256(blob).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(
            f"{SOURCE_URL} hashed {digest}, expected {SOURCE_SHA256}. The file changed "
            "under a fixed reference. Do not train on it until someone has looked at why."
        )
    return blob


def parse(blob: bytes) -> tuple[np.ndarray, np.ndarray]:
    """The eight features and the label, as float64 arrays, in file order."""
    import xlrd

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        sheet = xlrd.open_workbook(file_contents=archive.read(MEMBER)).sheet_by_index(0)

    # Row 0 is the X1..X23 banner, row 1 the real headers, data from row 2.
    header = [str(v).strip() for v in sheet.row_values(1)]
    for name in (*FEATURES, TARGET):
        if name not in header:
            raise RuntimeError(f"column {name!r} is not in the sheet; got {header}")

    columns = [header.index(name) for name in FEATURES]
    target = header.index(TARGET)

    rows = np.asarray(
        [sheet.row_values(r) for r in range(2, sheet.nrows)],
        dtype=np.float64,
    )
    return rows[:, columns], rows[:, target]


def load(cache: Path, test_fraction: float = 0.2, seed: int = 20261014) -> Dataset:
    """Downloads, parses, splits and standardises. Deterministic given the seed."""
    x, y = parse(download(cache))

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(x))
    cut = int(len(x) * (1.0 - test_fraction))
    train_idx, test_idx = order[:cut], order[cut:]

    raw_train, raw_test = x[train_idx], x[test_idx]
    mean = raw_train.mean(axis=0)
    std = raw_train.std(axis=0)
    std = np.where(std < 1e-12, 1.0, std)

    return Dataset(
        x_train=((raw_train - mean) / std),
        y_train=y[train_idx].astype(np.int64),
        x_test=((raw_test - mean) / std),
        y_test=y[test_idx].astype(np.int64),
        mean=mean,
        std=std,
        raw_test=raw_test,
    )
