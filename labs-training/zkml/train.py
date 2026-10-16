"""Trains Lab 05's credit-risk model and exports it for the circuit (doc 21 §11).

    cd labs-training
    uv run python -m zkml.train            # the real thing
    uv run python -m zkml.train --smoke    # tiny subset, few epochs, for CI

Doc 21 §11 sets the rule this script enforces: **ship the MLP only if it beats
logistic regression by at least 0.01 AUC, and record both numbers either way.**
That is a real gate, not a formality -- a two-layer network on eight features
is not obviously better than a linear model, and a zero-knowledge demo that
proves an unnecessary MLP is proving the wrong thing. If LR wins, the script
says so and the circuit should be built for LR.

Outputs, into ``--out``:

- ``zkml-model.json``  float and fixed-point weights, scaler, bucket cuts, metrics
- ``MODEL-CARD.md``    what it was trained on, what it scores, what it excludes
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from torch import nn

from .data import EXCLUDED_PROTECTED, FEATURES, SOURCE_SHA256, SOURCE_URL, load
from .fixedpoint import (
    CLAMP_SD,
    SCALE,
    SCALE_BITS,
    bucket,
    clamp,
    infer_fixed,
    infer_float,
    quantise_model,
)

HIDDEN = 8
MIN_AUC_GAIN = 0.01


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        return "unknown"


def _git_dirty() -> bool:
    try:
        return bool(
            subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
            ).stdout.strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        return True


class CreditMLP(nn.Module):
    """8 -> 8 (ReLU) -> 1, the shape doc 21 §11 names.

    Deliberately small. Every multiplication becomes constraints in the circuit,
    and the proving time the lab advertises is a function of that count.
    """

    def __init__(self, features: int, hidden: int = HIDDEN) -> None:
        super().__init__()
        self.fc1 = nn.Linear(features, hidden)
        self.fc2 = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out: torch.Tensor = self.fc2(torch.relu(self.fc1(x))).squeeze(-1)
        return out


def train_mlp(
    x: np.ndarray, y: np.ndarray, epochs: int, seed: int, clamp_sd: float
) -> tuple[CreditMLP, list[dict[str, float]]]:
    """Trains on clamped features, because clamped is what the circuit sees.

    Training on unclamped data and clamping only at inference would leave the
    network relying on tail values it will never be shown again.
    """
    torch.manual_seed(seed)
    model = CreditMLP(x.shape[1])
    optimiser = torch.optim.Adam(model.parameters(), lr=1e-2)
    # The dataset is about 22% positive; weighting the positive class stops the
    # network settling on "nobody defaults", which scores 78% accuracy and is
    # useless.
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((1 - y.mean()) / y.mean()))

    xt = torch.from_numpy(clamp(x, clamp_sd)).float()
    yt = torch.from_numpy(y).float()
    generator = torch.Generator().manual_seed(seed)
    history: list[dict[str, float]] = []

    for epoch in range(epochs):
        order = torch.randperm(len(xt), generator=generator)
        total = 0.0
        for start in range(0, len(xt), 256):
            idx = order[start : start + 256]
            optimiser.zero_grad()
            loss = loss_fn(model(xt[idx]), yt[idx])
            loss.backward()
            optimiser.step()
            total += float(loss.detach()) * len(idx)
        history.append({"epoch": epoch + 1, "loss": total / len(xt)})

    model.eval()
    return model, history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "uci-credit.zip",
    )
    args = parser.parse_args()
    epochs = 2 if args.smoke else args.epochs
    args.out.mkdir(parents=True, exist_ok=True)

    print("Loading the UCI credit-default dataset...")
    data = load(args.cache)
    x_train, y_train, x_test, y_test = data.x_train, data.y_train, data.x_test, data.y_test
    if args.smoke:
        x_train, y_train = x_train[:2000], y_train[:2000]
        x_test, y_test = x_test[:1000], y_test[:1000]
    print(f"  train {x_train.shape}  test {x_test.shape}  default rate {y_train.mean():.3f}")

    # How much of the data the clamp actually touches. Measured, because a
    # clamp that moved a tenth of the test set would be a modelling decision
    # masquerading as a numeric detail.
    clamped_values = int((np.abs(x_test) > CLAMP_SD).sum())
    clamped_rows = int((np.abs(x_test) > CLAMP_SD).any(axis=1).sum())
    print(
        f"  clamp at ±{CLAMP_SD} sd touches {clamped_values} of {x_test.size} test values "
        f"({clamped_values / x_test.size:.4%}) across {clamped_rows} rows"
    )

    print("Fitting logistic regression (the baseline the MLP has to beat)...")
    lr = LogisticRegression(max_iter=2000, class_weight="balanced").fit(
        clamp(x_train, CLAMP_SD), y_train
    )
    lr_auc = float(roc_auc_score(y_test, lr.decision_function(clamp(x_test, CLAMP_SD))))
    print(f"  logistic regression AUC {lr_auc:.4f}")

    print(f"Training the MLP ({x_train.shape[1]} -> {HIDDEN} -> 1, {epochs} epochs)...")
    model, history = train_mlp(x_train, y_train, epochs, args.seed, CLAMP_SD)
    with torch.no_grad():
        mlp_logits = model(torch.from_numpy(clamp(x_test, CLAMP_SD)).float()).numpy()
    mlp_auc = float(roc_auc_score(y_test, mlp_logits))
    print(f"  MLP AUC {mlp_auc:.4f}  (gain over LR {mlp_auc - lr_auc:+.4f})")

    ships_mlp = (mlp_auc - lr_auc) >= MIN_AUC_GAIN
    print(
        f"  doc 21 §11 gate: MLP must beat LR by ≥{MIN_AUC_GAIN:.2f} AUC -> "
        f"{'MLP ships' if ships_mlp else 'LR WINS, the MLP does not earn its constraints'}"
    )

    # --- fixed point -------------------------------------------------------
    w1 = model.fc1.weight.detach().numpy().T.astype(np.float64)
    b1 = model.fc1.bias.detach().numpy().astype(np.float64)
    w2 = model.fc2.weight.detach().numpy().ravel().astype(np.float64)
    b2 = float(model.fc2.bias.detach().numpy()[0])

    fixed = quantise_model(w1, b1, w2, b2, CLAMP_SD)
    fixed_logits_q = infer_fixed(fixed, x_test)
    float_logits = infer_float(w1, b1, w2, b2, x_test, CLAMP_SD)

    fixed_auc = float(roc_auc_score(y_test, fixed_logits_q.astype(np.float64)))
    sign_agreement = float((np.sign(fixed_logits_q) == np.sign(float_logits)).mean())
    bucket_agreement = float(
        (bucket(fixed_logits_q) == bucket((float_logits * SCALE).astype(np.int64))).mean()
    )
    max_logit_error = float(np.abs(fixed_logits_q / SCALE - float_logits).max())

    print("Float vs fixed-point agreement:")
    print(f"  AUC float {mlp_auc:.4f}  fixed {fixed_auc:.4f}  (delta {fixed_auc - mlp_auc:+.5f})")
    print(f"  same side of zero : {sign_agreement:.4%}")
    print(f"  same risk bucket  : {bucket_agreement:.4%}")
    print(f"  max logit error   : {max_logit_error:.3e}")

    metadata = {
        "$comment": (
            "Written by labs-training/zkml/train.py. Every number measured here; doc 21 §15 "
            "keeps targets and results separate and so does this file."
        ),
        "smoke": bool(args.smoke),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gitCommit": _git_sha(),
        "gitDirty": _git_dirty(),
        "seed": args.seed,
        "data": {
            "source": SOURCE_URL,
            "sha256": SOURCE_SHA256,
            "features": list(FEATURES),
            "excludedProtected": list(EXCLUDED_PROTECTED),
            "trainRows": len(x_train),
            "testRows": len(x_test),
            "defaultRate": float(y_train.mean()),
        },
        "scaler": {"mean": data.mean.tolist(), "std": data.std.tolist()},
        "fixedPoint": {
            "scaleBits": SCALE_BITS,
            "scale": SCALE,
            "clampSd": CLAMP_SD,
            "clampedTestValues": clamped_values,
            "clampedTestRows": clamped_rows,
            "rescale": "floor toward -infinity, as an arithmetic shift",
            "rounding": "half away from zero",
        },
        "models": {
            "logisticRegression": {"auc": lr_auc},
            "mlp": {
                "shape": [len(FEATURES), HIDDEN, 1],
                "aucFloat": mlp_auc,
                "aucFixed": fixed_auc,
                "epochs": epochs,
                "history": history[-5:],
            },
            "gate": {
                "minAucGain": MIN_AUC_GAIN,
                "actualGain": mlp_auc - lr_auc,
                "mlpShips": ships_mlp,
            },
        },
        "agreement": {
            "sameSideOfZero": sign_agreement,
            "sameBucket": bucket_agreement,
            "maxLogitError": max_logit_error,
        },
        "weights": {
            "float": {"w1": w1.tolist(), "b1": b1.tolist(), "w2": w2.tolist(), "b2": b2},
            "fixed": {
                "w1": fixed.w1.tolist(),
                "b1": fixed.b1.tolist(),
                "w2": fixed.w2.tolist(),
                "b2": fixed.b2,
                "$comment": "w at 2^16, b at 2^32 (the scale the accumulator is at).",
            },
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
        },
    }
    (args.out / "zkml-model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"\nWrote {args.out / 'zkml-model.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
