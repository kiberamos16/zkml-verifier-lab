#!/usr/bin/env node
// Turns a real snarkjs proof into the JSON the Foundry test reads.
//
// The test needs the proof as flat uint arrays, and snarkjs emits either a
// proof object or a blob of Solidity calldata. Neither is directly parseable
// by `vm.parseJsonUintArray`, so this converts once, here, rather than leaving
// a hand-transcribed fixture in the test file where a typo would look like a
// verifier bug.
//
//   node scripts/labs/zkml-fixture.mjs \
//     circuits/zkml/ceremony/proof.json \
//     circuits/zkml/ceremony/public.json \
//     contracts/zkml/test/fixture.json

import { readFile, writeFile } from 'node:fs/promises';
import { argv } from 'node:process';

const [, , proofPath, publicPath, outPath] = argv;
if (!proofPath || !publicPath || !outPath) {
  console.error('usage: zkml-fixture.mjs <proof.json> <public.json> <out.json>');
  process.exit(1);
}

const proof = JSON.parse(await readFile(proofPath, 'utf8'));
const publicSignals = JSON.parse(await readFile(publicPath, 'utf8'));

if (proof.protocol !== 'groth16') {
  console.error(`expected a groth16 proof, got ${proof.protocol}`);
  process.exit(1);
}

// snarkjs writes pi_b with its two field coefficients in the opposite order to
// the one the Solidity verifier expects. Getting this backwards produces a
// proof that fails to verify for a reason nothing explains, so it is done in
// one place and noted here.
const fixture = {
  pA: [proof.pi_a[0], proof.pi_a[1]],
  pB0: [proof.pi_b[0][1], proof.pi_b[0][0]],
  pB1: [proof.pi_b[1][1], proof.pi_b[1][0]],
  pC: [proof.pi_c[0], proof.pi_c[1]],
  pubSignals: publicSignals,
};

await writeFile(outPath, `${JSON.stringify(fixture, null, 2)}\n`);
console.log(`wrote ${outPath} with ${publicSignals.length} public signals`);
