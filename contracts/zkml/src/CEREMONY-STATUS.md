# Which ceremony produced `Groth16Verifier.sol`?

**The completed 2026-10-16 ceremony. Sepolia deployment verified.**

The verifier and `test/fixture.json` were regenerated from `credit_final.zkey`,
following Sebastian's contribution and Ethereum mainnet beacon block **26205728**.
The target was precommitted in `07826a3` before mining and its hash was applied
only after finalization. Full transcript: `circuits/zkml/ceremony/CEREMONY.md`.

Final zkey SHA-256: `6202cf8331c311669f25dca89a211e25c060464438321ac0637dde21a55898ee`.

The final zkey chain verifies, its generated proof verifies, and all six
Foundry verifier tests pass, including the tampered and zero-proof cases.
This contract replaces the previous development-beacon verifier. Deployed on Sepolia
at `0x90737933594686BAC98cEB1B600Cc3876c4DC591`, transaction
`0x88abfe2ff3ffe3eaa926e7bc6a3ae385a666df748f980d5831f06f5c57ca583d`,
block 11928453. Runtime bytecode matches the local compiled artifact exactly.
Read-only calls accept the real fixture and reject a changed public signal.
Etherscan source verification passed on 2026-10-16. Public GPL-3.0 source mirror: https://github.com/kiberamos16/zkml-verifier-lab. Evidence: `docs/evidence/2026-10-16-verifier-deployment.json`.
