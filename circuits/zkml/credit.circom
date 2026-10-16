pragma circom 2.1.9;

include "../../node_modules/circomlib/circuits/poseidon.circom";
include "fixedpoint.circom";

/*
 * Lab 05 · Zero-Knowledge Inference — credit-risk MLP in a Groth16 circuit.
 *
 * Doc 21 §11. The circuit proves: "I ran *this* model on *some* inputs, and it
 * produced this prediction and this bucket" -- without revealing either the
 * inputs or the weights.
 *
 *   private : the eight features, a salt, and every weight and bias
 *   public  : modelCommitment, inputCommitment, prediction, bucket
 *
 * The two commitments are what stop the proof being vacuous. Without them a
 * prover could invent whatever weights produce the answer they want and the
 * verifier would accept it, because the weights are private. Binding them to a
 * Poseidon hash that is published in advance turns "some model" into "the
 * model whose commitment is on the page".
 *
 * The salt is what stops the input commitment being brute-forcible. Eight
 * standardised credit features have far too little entropy to hide behind a
 * hash on their own -- an attacker with the commitment could simply try
 * plausible inputs until one matched.
 *
 * Arithmetic matches labs-training/zkml/fixedpoint.py exactly: scale 2^16,
 * rounding half away from zero (done outside, when the witness is built),
 * rescaling that floors toward negative infinity. The Python's agreement check
 * is what proves the two stay in step.
 */

/*
 * Poseidon over more inputs than one permutation takes.
 *
 * circomlib's Poseidon caps at 16 inputs; the model has 81 numbers in it. They
 * are absorbed in chunks with the running digest carried into the next chunk,
 * which is a standard sponge-style chain. The chunk size is 15 rather than 16
 * precisely because the digest occupies the first slot.
 */
template PoseidonChain(N) {
    signal input in[N];
    signal output out;

    var CHUNK = 15;
    var CHUNKS = (N + CHUNK - 1) \ CHUNK;

    component round[CHUNKS];
    signal running[CHUNKS + 1];
    running[0] <== 0;

    for (var c = 0; c < CHUNKS; c++) {
        round[c] = Poseidon(16);
        round[c].inputs[0] <== running[c];
        for (var i = 0; i < CHUNK; i++) {
            var index = c * CHUNK + i;
            // The tail is zero-padded. The length is fixed by the template
            // parameter, so padding cannot be confused with data.
            if (index < N) {
                round[c].inputs[i + 1] <== in[index];
            } else {
                round[c].inputs[i + 1] <== 0;
            }
        }
        running[c + 1] <== round[c].out;
    }

    out <== running[CHUNKS];
}

/*
 * FEATURES  inputs the visitor fills in
 * HIDDEN    width of the single hidden layer
 * SCALE     fixed-point shift, 16 per doc 21 §11
 * ACC_BITS  bound on any accumulator, as a signed value
 *
 * ACC_BITS is not a free parameter. Features are clamped to ±8 standard
 * deviations, so |x| <= 8 * 2^16 < 2^20. Weights stay well under 4, so
 * |w| < 2^18. A product is then under 2^38, a sum of eight under 2^41, and the
 * bias (carried at 2^32) cannot lift it past 2^42. The second layer repeats
 * the shape on smaller numbers. 48 leaves six bits of headroom and keeps the
 * Num2Bits decompositions cheap; the Python asserts the same bound on real
 * data so a violation shows up in training rather than as an unsatisfiable
 * witness here.
 */
template CreditRisk(FEATURES, HIDDEN, SCALE, ACC_BITS) {
    // --- private --------------------------------------------------------
    signal input features[FEATURES];
    signal input salt;
    signal input w1[FEATURES][HIDDEN];
    signal input b1[HIDDEN];
    signal input w2[HIDDEN];
    signal input b2;

    // --- public ---------------------------------------------------------
    signal input lowCut;
    signal input highCut;

    // The commitments are OUTPUTS, not inputs the circuit checks against.
    //
    // Both shapes give the same guarantee and this one needs no Poseidon
    // outside the circuit. As an input, the prover would supply the hash and
    // the circuit would assert its own computation matched -- which means the
    // caller has to reimplement Poseidon to build a witness at all. As an
    // output it lands in the public signals, and the verifier does the binding
    // where the binding belongs: by checking the signal equals the commitment
    // published alongside the model. A prover who swaps the weights produces a
    // different commitment and fails that check.
    signal output modelCommitment;
    signal output inputCommitment;
    signal output prediction;
    signal output bucket;

    // --- bind the private values to the published commitments -----------
    // Order is part of the interface: the Python writes the weights into the
    // commitment in exactly this order, and a different order is a different
    // hash and a proof that will not verify.
    var MODEL_LEN = FEATURES * HIDDEN + HIDDEN + HIDDEN + 1;
    component modelHash = PoseidonChain(MODEL_LEN);
    var at = 0;
    for (var i = 0; i < FEATURES; i++) {
        for (var j = 0; j < HIDDEN; j++) {
            modelHash.in[at] <== w1[i][j];
            at++;
        }
    }
    for (var j = 0; j < HIDDEN; j++) { modelHash.in[at] <== b1[j]; at++; }
    for (var j = 0; j < HIDDEN; j++) { modelHash.in[at] <== w2[j]; at++; }
    modelHash.in[at] <== b2;
    modelCommitment <== modelHash.out;

    component inputHash = PoseidonChain(FEATURES + 1);
    for (var i = 0; i < FEATURES; i++) { inputHash.in[i] <== features[i]; }
    inputHash.in[FEATURES] <== salt;
    inputCommitment <== inputHash.out;

    // --- layer 1 --------------------------------------------------------
    // Products land at scale 2^32; the bias is supplied already at 2^32, so
    // the whole accumulator is at one scale and a single rescale per unit is
    // enough. Doing it per product would cost HIDDEN * FEATURES divisions and
    // round eight times as often.
    signal acc1[HIDDEN][FEATURES + 1];
    component shift1[HIDDEN];
    component relu[HIDDEN];
    signal hidden[HIDDEN];

    for (var j = 0; j < HIDDEN; j++) {
        acc1[j][0] <== b1[j];
        for (var i = 0; i < FEATURES; i++) {
            acc1[j][i + 1] <== acc1[j][i] + w1[i][j] * features[i];
        }
        shift1[j] = SignedShiftRight(ACC_BITS, SCALE);
        shift1[j].in <== acc1[j][FEATURES];

        relu[j] = SignedReLU(ACC_BITS);
        relu[j].in <== shift1[j].out;
        hidden[j] <== relu[j].out;
    }

    // --- layer 2 --------------------------------------------------------
    signal acc2[HIDDEN + 1];
    acc2[0] <== b2;
    for (var j = 0; j < HIDDEN; j++) {
        acc2[j + 1] <== acc2[j] + w2[j] * hidden[j];
    }

    component shift2 = SignedShiftRight(ACC_BITS, SCALE);
    shift2.in <== acc2[HIDDEN];
    prediction <== shift2.out;

    component risk = Bucket(ACC_BITS);
    risk.in <== prediction;
    risk.lowCut <== lowCut;
    risk.highCut <== highCut;
    bucket <== risk.out;
}

component main {public [lowCut, highCut]} = CreditRisk(8, 8, 16, 48);
