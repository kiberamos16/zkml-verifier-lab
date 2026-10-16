# The Collection ZK verifier lab

Public GPL-3.0 source mirror for the finalized circuit and Sepolia verifier.

Sepolia address: `0x90737933594686BAC98cEB1B600Cc3876c4DC591`.

Toolchain: circom 2.2.3, circomlib 2.0.5, snarkjs 0.7.6, Foundry 1.8.5, solc 0.8.30.

Install snarkjs/circomlib with npm, compile circuits with circom and `-l node_modules`. Follow circuits/zkml/ceremony/CEREMONY.md for setup/proof reproduction. Install foundry-rs/forge-std into contracts/zkml/lib/forge-std, then run `forge test --root contracts/zkml`.

This is a demonstration, not a lending or credit decision service.
