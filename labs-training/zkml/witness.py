"""Builds the circuit's inputs from a trained model and a row of features.

The browser will do this in TypeScript at L05.4; this is the reference, and
the place the agreement is proved. Two things here are easy to get wrong and
produce a proof that verifies against the wrong statement rather than an
error:

**Negative numbers.** A circom signal is a field element. There is no -3; there
is p - 3, which is a 254-bit positive integer. Every signed value therefore has
to be mapped into the field on the way in, and mapped back on the way out --
and "on the way out" matters, because a prediction of -1 comes back as a number
near p and will look like an enormous positive logit to anything that forgets.

**Commitment ordering.** The model commitment hashes 81 numbers. The circuit
absorbs them in a fixed order and so must this; a different order is a
different hash and a proof that simply will not verify, with nothing to say
why.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

# The BN254 scalar field circom and snarkjs work over.
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def to_field(value: int) -> str:
    """A signed Python integer as a field element, decimal, for the input JSON."""
    return str(int(value) % FIELD)


def from_field(value: int | str) -> int:
    """A field element back to the signed integer it stands for.

    Anything in the upper half of the field is read as negative, which is the
    convention the circuit's range checks enforce.
    """
    v = int(value) % FIELD
    return v - FIELD if v > FIELD // 2 else v


def model_values(model: dict[str, Any]) -> list[int]:
    """The 81 numbers of the model commitment, in the circuit's order.

    w1 row-major (feature-major, matching `for i in FEATURES: for j in HIDDEN`),
    then b1, then w2, then b2.
    """
    fixed = model["weights"]["fixed"]
    values: list[int] = []
    for row in fixed["w1"]:
        values.extend(int(v) for v in row)
    values.extend(int(v) for v in fixed["b1"])
    values.extend(int(v) for v in fixed["w2"])
    values.append(int(fixed["b2"]))
    return values


def build(model: dict[str, Any], features_q: np.ndarray, salt: int) -> dict[str, Any]:
    """The circuit input object, ready to be written as JSON.

    `features_q` is already quantised and clamped -- the same integers
    `infer_fixed` consumes, so the circuit and the Python are fed identically.
    """
    from .fixedpoint import SCALE, quantise

    fixed = model["weights"]["fixed"]
    low = int(quantise(np.asarray(-1.0)))
    high = int(quantise(np.asarray(0.0)))
    assert SCALE == model["fixedPoint"]["scale"]

    return {
        "features": [to_field(int(v)) for v in features_q],
        "salt": to_field(salt),
        "w1": [[to_field(int(v)) for v in row] for row in fixed["w1"]],
        "b1": [to_field(int(v)) for v in fixed["b1"]],
        "w2": [to_field(int(v)) for v in fixed["w2"]],
        "b2": to_field(int(fixed["b2"])),
        "modelCommitment": "0",  # filled in by the caller once Poseidon is run
        "inputCommitment": "0",
        "lowCut": to_field(low),
        "highCut": to_field(high),
    }


def load_model(path: Path) -> dict[str, Any]:
    model: dict[str, Any] = json.loads(path.read_text())
    if model.get("smoke"):
        raise SystemExit(f"{path} came from a --smoke run; retrain before proving against it.")
    return model
