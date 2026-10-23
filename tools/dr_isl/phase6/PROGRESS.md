# Phase 6 durable progress

- Base verified: HEAD `61e29cabd085404cf3dd600b4c535d5a0c08f899`; application changes match `46cd09c`, with Phase 5b tests at `8f73e38`.
- Initial tree status was clean. No Phase 6 evidence runs have been performed yet.
- 6.0 implementation candidate is in the working tree. Focused verification: `tests/test_dr_isl_frequency_feedback.py` plus `test_acceptance_has_fixed_enumeration_and_fails_worse_informed` — 16 passed.
- Explicit-seed gate, base demo (`scenario-uneven-multisched-01`, seed 42): complete. Baseline physical SHA-256 `e9a25202a069acdb648779981f07bc27e1cbe53a5a2b44e1571bd8724912a5f9`; informed `34bc07cdebda13c4e07bc990408745fbeeb5f916248cd7159d9f8fd656ee2702`. The stored Phase 5b metric values matched; compare_runs stayed PASS 10/10 with the same condition order and booleans. H1/H2 are still running.
- H1-24h pair completed: baseline physical SHA-256 `249a9925b8f97e20db79cf6f02bf0c282f2f57ec825026af0ec183a0d4dad7f1`; informed `0c929bba5ae33582779fc3790b9e66b4d48ed17820a70bdb9885c12db40cc6f7`. Both match Phase 5b hashes and stored metric values. `compare_runs` remains PASS 10/10 with unchanged condition order and booleans. H2 pair is pending.
- H2-24h pair completed: baseline physical SHA-256 `3f39c1e60e3b1b30eb51455b50c2c429947f24955a9744e2d22680a86c5b524e`; informed `85aff01fe0a381f3438c6e9cdf53c942501ea1585d72d3dbf6c1f9992ea62ee4`. Both match Phase 5b hashes and stored metric values. `compare_runs` remains PASS 10/10 with unchanged condition order and booleans.
- 6.0 gate complete: all six explicit-seed arm hashes match Phase 5b; all stored comparison metric values and all 10 comparison conditions match. Full per-tick hash equality plus unchanged metric implementation verifies the original metrics are unchanged. Evidence: `6_0_EXPLICIT_STUDY_CHECK.json`; `all_passed=true`.
- Focused test verification after the final 6.0 test edit: 16 passed (`tests/test_dr_isl_frequency_feedback.py` plus `test_acceptance_has_fixed_enumeration_and_fails_worse_informed`).
- D4 inventory/implementation has not started.
