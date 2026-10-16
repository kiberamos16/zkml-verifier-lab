pragma circom 2.1.9;

include "../../node_modules/circomlib/circuits/comparators.circom";
include "../../node_modules/circomlib/circuits/bitify.circom";

/*
 * Fixed-point arithmetic over a prime field, matching
 * labs-training/zkml/fixedpoint.py operation for operation.
 *
 * The field has no negative numbers and no division. A value we think of as
 * -3 is represented as p - 3, which is an enormous positive integer, so every
 * comparison and every shift has to say explicitly what range it expects. That
 * is what the OFFSET below is for: a signed value known to satisfy
 * |v| < 2^(BITS-1) is shifted into [0, 2^BITS) before anything looks at its
 * bits, and shifted back afterwards.
 *
 * Getting a bound wrong here does not produce a wrong answer -- it produces a
 * circuit that is satisfiable by a value nobody intended, which is a soundness
 * bug. Every template below therefore range-checks its own inputs rather than
 * trusting its caller.
 */

/*
 * Divides a signed value by 2^SHIFT, flooring toward negative infinity.
 *
 * This is the "range-checked rescaling" doc 21 §11 asks for. The quotient and
 * remainder come from the witness; the constraints are what make them the
 * right ones:
 *
 *   shifted === q * 2^SHIFT + r     with   0 <= r < 2^SHIFT
 *
 * The remainder is decomposed into exactly SHIFT bits, which is what pins it
 * below 2^SHIFT. Without that constraint a prover could choose r = 2^SHIFT and
 * q one lower, and the circuit would happily prove a different number.
 *
 * Flooring rather than truncating matters: Python's `//` and an arithmetic
 * shift both send -1 >> 16 to -1, while C-like division sends it to 0. The
 * Python port floors, so this floors, and the two agree on negative
 * activations instead of disagreeing on half of them.
 */
template SignedShiftRight(BITS, SHIFT) {
    signal input in;
    signal output out;

    var OFFSET = 1 << (BITS - 1);

    // Shift into non-negative territory, then prove the result really does fit
    // in BITS bits -- which is also what proves the caller's claim about |in|.
    signal shifted;
    shifted <== in + OFFSET;

    component bound = Num2Bits(BITS);
    bound.in <== shifted;

    signal quotient;
    signal remainder;
    quotient <-- shifted >> SHIFT;
    remainder <-- shifted & ((1 << SHIFT) - 1);

    component remainderBits = Num2Bits(SHIFT);
    remainderBits.in <== remainder;

    component quotientBits = Num2Bits(BITS - SHIFT);
    quotientBits.in <== quotient;

    shifted === quotient * (1 << SHIFT) + remainder;

    // Undo the offset. It was chosen as a power of two at least 2^SHIFT, so
    // the division of the offset itself is exact and introduces no rounding.
    out <== quotient - (OFFSET >> SHIFT);
}

/*
 * max(0, in), for a signed value that fits in BITS bits.
 *
 * `LessThan` needs both operands below 2^n, so the comparison happens on the
 * offset value rather than on the signed one.
 */
template SignedReLU(BITS) {
    signal input in;
    signal output out;

    var OFFSET = 1 << (BITS - 1);

    component isNegative = LessThan(BITS);
    isNegative.in[0] <== in + OFFSET;
    isNegative.in[1] <== OFFSET;

    // One multiplication, so one constraint: zero when negative, in otherwise.
    out <== in * (1 - isNegative.out);
}

/*
 * Which of three risk buckets a logit falls in: 0 low, 1 medium, 2 high.
 *
 * The circuit has no sigmoid, so the cuts are on the fixed-point logit itself,
 * exactly as `bucket()` does in the Python.
 */
template Bucket(BITS) {
    signal input in;
    signal input lowCut;
    signal input highCut;
    signal output out;

    var OFFSET = 1 << (BITS - 1);

    component belowLow = LessThan(BITS);
    belowLow.in[0] <== in + OFFSET;
    belowLow.in[1] <== lowCut + OFFSET;

    component belowHigh = LessThan(BITS);
    belowHigh.in[0] <== in + OFFSET;
    belowHigh.in[1] <== highCut + OFFSET;

    // 0 when below the low cut, 1 when between, 2 when at or above the high
    // cut. Written as a sum of indicators so it stays linear.
    out <== 2 - belowLow.out - belowHigh.out;
}
