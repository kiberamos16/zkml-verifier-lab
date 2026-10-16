# Lab 05 · Groth16 ceremony transcript

> **STATUS: CEREMONY COMPLETE · 2026-10-16.** Sebastian contributed, the
> precommitted Ethereum mainnet block 26205728 finalized, and its hash was
> applied with beacon exponent 10. The committed verifier and proof fixture
> now come from this final ceremony. Sepolia deployment is still pending.

## Phase 1 — Powers of Tau

Doc 21 §11 asks for "the public Hermez/Polygon Powers of Tau file of the
smallest sufficient size (hash checked)". The circuit has 16,175 constraints,
so 2^15 (32,768) is the smallest that fits.

| | |
|---|---|
| File | `powersOfTau28_hez_final_15.ptau` |
| Source | `https://circom.info/powersOfTau28_hez_final_15.ptau` |
| Size | 36 MB |
| SHA-256 | `3ef2ecc5b75d687048cf2d59195119b42fb07c5af639c5f283d84bfa69829e7f` |

**The URL is not the one doc 21 implies, and that is worth recording.** Both
addresses the Hermez ceremony was originally published at —
`hermez.s3-eu-west-1.amazonaws.com` and `storage.googleapis.com/zkevm/ptau` —
now return **403**. The files were rehosted; snarkjs's own README points at
`circom.info`, which is where this came from.

That also means the publisher's hash list is no longer reachable, so the
SHA-256 above is **what we observed**, not something checked against an
independent publication. The real assurance is cryptographic rather than
bibliographic: `snarkjs zkey verify` checks the zkey against this ptau and the
r1cs together, and it passes ("ZKey Ok!"). A full `powersoftau verify` of the
whole 2^28 transcript was attempted and abandoned after it stalled at 0% CPU
for eleven minutes; it is not a cheap operation and it is not what protects us
here.

## Phase 2 — circuit-specific setup

Circuit hash (snarkjs, blake2b):

```
ee2402dc 802e8c13 fb7aad10 6d2a5aff
7fd89185 76826273 9cd53715 b198584e
addd05ac 0523a705 19ea2945 52ff008d
949b7265 43b6dab9 ba4d279c a049db43
```

| # | Contributor | Hash |
|---|---|---|
| 1 | `claude-build-machine-2026-10-14` | `e21f4809 2c1849a7 71b5a8b7 d1f497bb …` |
| 2 | `sebastian-2026-10-16` — verified with `snarkjs zkey verify` on 2026-10-16 | `8e7d4c48 23720753 22c0d00e 50d57260 …` |
| beacon | Ethereum mainnet block `26205728`, finalized before application | `f8bf08f2 098bb61d 738ba488 4104cfcf …` |

Contribution 1 used 64 bytes from `/dev/urandom`. The entropy was passed on the
command line and never written anywhere; it is gone, which is the point of a
contribution — the setup is secure as long as *at least one* contributor
discarded theirs.

## Reproducing

```bash
cd circuits/zkml
circom credit.circom --r1cs --wasm --sym -o .
cd ceremony
curl -L -o ptau15.ptau https://circom.info/powersOfTau28_hez_final_15.ptau
snarkjs groth16 setup ../credit.r1cs ptau15.ptau credit_0000.zkey
snarkjs zkey contribute credit_0000.zkey credit_0001.zkey --name="<who>" -e="<entropy>"
snarkjs zkey verify ../credit.r1cs ptau15.ptau credit_0001.zkey
```

The `.ptau`, the zkeys, the witness and the compiled circuit are gitignored.
The circuit and witness can be rebuilt, but the contributed zkeys cannot be
reproduced byte for byte after contributors discard their entropy. Preserve
`credit_0002.zkey` and the completed `credit_final.zkey`; a fresh setup would
produce a different verifier. The transcript records hashes for integrity checks.

## Measured, on this machine, through Node

| Step | Time |
|---|---|
| Witness generation | 138 ms |
| `groth16 prove` | 815 ms |
| `groth16 verify` | 231 ms |
| `verifyProof` on-chain | 258,385 gas |

Doc 21 §11's target is **850 ms for a proof on the M1 Pro**. The 815 ms above is
Node on this machine, **not** the browser, and browser WASM is slower — so this
is an encouraging lower bound and not the number the lab will report. L05.4
measures the real one in a worker and shows that.


## Sebastian contribution verification · 2026-10-16

`credit_0002.zkey` verified against `credit.r1cs` and the documented `ptau15.ptau`: **ZKey Ok!** Circuit hash and contribution 1 match the existing transcript. Contribution 2 hash:

```text
8e7d4c48 23720753 22c0d00e 50d57260
e2f7ef06 fc307565 121debef 39fb7714
a3fbcf3f 12c48406 69bc7a55 2dd4d895
e467638a 16910141 e4d30eb3 ea96b979
```

The user entered entropy directly in a local terminal with echo disabled. It was not provided to the assistant. At this verification checkpoint the beacon was pending. The final beacon and regenerated verifier are recorded below.


## Beacon precommitment · 2026-10-16T14:31:19.901846+00:00

Sebastian authorized selection and completion on 2026-10-16. The selected Ethereum **mainnet block is 26205728**, chosen while the live head was 26205708 (hash `0x0632f04865cab7be660d5c52bbdaec13ca7647f9a86bcdbe4e6ab965cc9047a5`, timestamp 1792161059). The target was 20 blocks in the future at selection. Use its canonical hash only after it is finalized; do not replace the target based on the resulting hash.

Input `credit_0002.zkey` SHA-256: `9e6c05134ea19c27894f1bac012f7bf61556813de12925c54a61d6fe41cf8e9b`. Beacon iteration exponent: **10**, as required by doc 23 §3.11. Apply the 32-byte block hash without the `0x` prefix. Output: `credit_final.zkey`.


## Final beacon and verification · 2026-10-16

- Precommitment: Git commit `07826a3`, recorded at `2026-10-16T14:31:19Z`.
- Selected mainnet block: **26205728**, mined at `2026-10-16T14:34:59Z`.
- Finalized height observed before application: **26205755**.
- Block hash: `0x4028e3855efffce642d5570f79866b90e658a57bef57d496e4acdcd3de845421`.
- Input was checked against the precommitted SHA-256 before beacon application.
- Beacon exponent: **10**.
- Final `credit_final.zkey` SHA-256: `6202cf8331c311669f25dca89a211e25c060464438321ac0637dde21a55898ee`.
- `credit_final_vkey.json` SHA-256: `4a6f539b3fae1f75bcef17479add74be84d2c9ffda96b307fc52256ac96f1e79`.

Final setup verification: **ZKey Ok!**, with both human/machine contributions
and the expected beacon in the chain. A fresh proof from the final key verified
with snarkjs. The Solidity verifier and Foundry fixture were regenerated from
that same final key; **all 6 Foundry tests passed**, including rejection of a
changed prediction, changed commitment, altered proof and all-zero proof.
The circuit rebuilt from the current source matches the recovered R1CS byte for
byte, and the witness passes `snarkjs wtns check`.

To reproduce the deterministic beacon from the preserved contributed key:

```bash
node ../../../node_modules/snarkjs/build/cli.cjs zkey beacon \
  credit_0002.zkey credit_final.zkey \
  4028e3855efffce642d5570f79866b90e658a57bef57d496e4acdcd3de845421 10 \
  -n="ethereum mainnet block 26205728"
```

Keep the contributed and final zkeys: their hashes are public, but the files
are gitignored and have not yet been distributed as browser artifacts. No
contract deployment or public circuit-repository mirror was performed here;
those remain L05.3.
