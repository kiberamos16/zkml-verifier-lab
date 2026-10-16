"""Fixed-point arithmetic that a circom circuit can reproduce exactly.

Doc 21 §11: "Fixed point: scale 2^16 with range-checked rescaling." This module
is the Python half of that, and the lab's "Check agreement" button measures the
float model against it on 1,000 test rows.

**Why this cannot be approximate.** A Groth16 circuit proves an integer
computation over a prime field. It has no floats, no division and no `max`.
Every operation here is one the circuit performs the same way, in the same
order, with the same rounding -- otherwise the proof would attest to a
computation that disagrees with the number the page displays, which is the one
thing a zero-knowledge demo must not do.

The rules, each of which the circuit mirrors:

- **Scale 2^16.** A value `v` is carried as the integer `round(v * 65536)`.
- **Products double the scale.** `w_q * x_q` is at 2^32, so the bias is stored
  pre-scaled to 2^32 and added there, before a single rescale per layer.
- **Rescaling floors toward negative infinity**, which is an arithmetic shift,
  not truncation toward zero. Python's `//` already does this; C-like `/` does
  not, and a circuit written the other way would disagree on every negative
  activation.
- **Inputs are clamped** before quantisation. The circuit bounds every signal
  with `Num2Bits`, so an unbounded input is not representable at all; and this
  dataset's payment columns reach 69 standard deviations, which would otherwise
  overflow the chosen width. The clamp is part of the model, so the float side
  applies it too -- comparing a clamped circuit against an unclamped float
  reference would measure the clamp rather than the quantisation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Doc 21 §11 fixes the scale.
SCALE_BITS = 16
SCALE = 1 << SCALE_BITS

# Standard deviations at which inputs are clamped. Chosen so that the widest
# intermediate stays inside the bit width the circuit range-checks: with 8
# features at 2^16, a clamp of 8 keeps every product under 2^(16+3+16) and the
# layer sum under 2^38, comfortably inside the 64-bit Num2Bits budget while
# leaving room for the second layer. Measured against the data in train.py,
# which records how many values it actually touches.
CLAMP_SD = 8.0


@dataclass(frozen=True)
class FixedModel:
    """An MLP 8 -> 8 (ReLU) -> 1, entirely in integers.

    Weights are at scale 2^16; biases at 2^32, because that is the scale the
    accumulator is at when they are added.
    """

    w1: np.ndarray  # int64 [8, 8] at 2^16
    b1: np.ndarray  # int64 [8]    at 2^32
    w2: np.ndarray  # int64 [8]    at 2^16
    b2: int  # at 2^32
    clamp_sd: float = CLAMP_SD

    @property
    def hidden(self) -> int:
        return int(self.w1.shape[1])


def clamp(x: np.ndarray, clamp_sd: float = CLAMP_SD) -> np.ndarray:
    """Bounds standardised features to what the circuit can represent."""
    bounded: np.ndarray = np.clip(x, -clamp_sd, clamp_sd)
    return bounded


def quantise(x: np.ndarray, scale: int = SCALE) -> np.ndarray:
    """Rounds to the nearest integer at the given scale, half away from zero.

    `np.round` is half-to-even, which would disagree with the circuit's
    witness generator on exact halves. Spelling the rule out costs nothing and
    removes a class of one-bit mismatch that is miserable to find later.
    """
    scaled = np.asarray(x, dtype=np.float64) * scale
    return np.floor(np.abs(scaled) + 0.5).astype(np.int64) * np.sign(scaled).astype(np.int64)


def rescale(v: np.ndarray, scale: int = SCALE) -> np.ndarray:
    """Brings an accumulator back down one scale, flooring toward -infinity."""
    return np.floor_divide(np.asarray(v, dtype=np.int64), scale)


def quantise_model(
    w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: float, clamp_sd: float = CLAMP_SD
) -> FixedModel:
    """Turns trained float weights into the integers the circuit carries."""
    return FixedModel(
        w1=quantise(w1),
        b1=quantise(b1, SCALE * SCALE),
        w2=quantise(w2),
        b2=int(quantise(np.asarray(b2), SCALE * SCALE)),
        clamp_sd=clamp_sd,
    )


def infer_fixed(model: FixedModel, x: np.ndarray) -> np.ndarray:
    """The circuit's computation, on standardised (unquantised) features.

    Returns the output logit at scale 2^16, as an integer -- the same value the
    circuit exposes as a public signal.
    """
    x_q: np.ndarray = quantise(clamp(x, model.clamp_sd))

    # Layer 1: products at 2^32, bias already at 2^32, one rescale to 2^16.
    acc: np.ndarray = x_q @ model.w1 + model.b1
    h = rescale(acc)
    # ReLU, which the circuit does with LessThan against zero.
    h = np.maximum(h, 0)

    # Layer 2: same shape of operation, down to a single logit.
    out: np.ndarray = h @ model.w2 + model.b2
    return rescale(out)


def infer_float(
    w1: np.ndarray, b1: np.ndarray, w2: np.ndarray, b2: float, x: np.ndarray, clamp_sd: float
) -> np.ndarray:
    """The same network in floating point, with the same clamp.

    The clamp is applied here too. Comparing a clamped circuit against an
    unclamped reference would measure the clamp instead of the quantisation,
    and the agreement number the lab prints is about the quantisation.
    """
    x_c = clamp(x, clamp_sd)
    out: np.ndarray = np.maximum(x_c @ w1 + b1, 0.0) @ w2 + b2
    return out


def bucket(logit_q: np.ndarray) -> np.ndarray:
    """Score bucket from the fixed-point logit: 0 low, 1 medium, 2 high risk.

    Cut at fixed-point logits rather than probabilities, because the circuit
    has no sigmoid -- it compares the logit against two constants with
    `LessThan`. The cuts correspond to probabilities of about 0.27 and 0.50.
    """
    low = quantise(np.asarray(-1.0))
    high = quantise(np.asarray(0.0))
    return np.where(logit_q < low, 0, np.where(logit_q < high, 1, 2)).astype(np.int64)
