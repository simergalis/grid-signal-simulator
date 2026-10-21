# D9c H identity map

Controlled comparison: engine/harness commit 869d55bbdfa1ce16e6e1514ade9a6ca4ca3a0442 held fixed; seed metadata None; interval 5.0 s.
Only input change: diesel_power_block.delta_t_start_s 3600.0 -> 10.0.
No H ScenarioSpec validation; no frozen legacy scenario. Actual H expansion path unchanged.
These isolate the D9c cache reset; subsequent source-commit changes also participate in production identities.

| Scenario | Arm | Old digest | New digest |
|---|---|---|---|
| scenario-h1-k8s-ray-24h | baseline | cb5defdcfb3367e3b2f8d0c126ef21af201b62d4d261893f9ecfce6e8d19925a | d8813756114b33e2c48fd267531795f433112640bf096adf83e54c7108a443e4 |
| scenario-h1-k8s-ray-24h | informed | bda7cab1d84991324c1b2175a4e2e85026896df37ff060b2a0b9ca7377001a57 | 5e27d7b9b734299b6ef613c88667826fea5218cd402a5910d22bee052cd9f8db |
| scenario-h1-k8s-ray-7d | baseline | 439e7044d457faf04e4eb4d3792495d071022311280d6f8ec596554db055fac6 | 23f4fa5911aff98c77e37d42529bb5782219295f5511be9d2fe26d4b07ced635 |
| scenario-h1-k8s-ray-7d | informed | 2b91e1bd173971ffd139cade2fb83c25adb0d3b125b52ede1f1de5dc261e64dd | 60cae3fd33c450ae93bf86ce46d7b5bf9d0d3d5091a4cfa05d840dd2ae7965c3 |
| scenario-h2-slurm-24h | baseline | 52a83f88c8b1b1ca7bcfa890e0da3185930f2e8c1bcbbf06a4e30fa006c2893c | ab014bb4e9ff8a7eb76bafbeab08aa471b70267a934cdff34b770ad26700347f |
| scenario-h2-slurm-24h | informed | 760ebcf2e2f7d4aeb175aeb5dd470f1ea150b61888e7e287059fae3b04a30685 | c0404784a7673fb23558955a0c705da3bb1c26cc9ff6c1329fddcf4bf69376d6 |
| scenario-h2-slurm-7d | baseline | d2686e54b265d9c82a12a980c44db3144c2bee185648c6ae23f118df88d3d1d7 | b75e36ed492921092abe61c66a6ddc9f5134cf70a8e5374e4fccf102b0f787e9 |
| scenario-h2-slurm-7d | informed | 1e8ed14c287fe22b803a59ea584148924ef25e8d25a766a0ab4ec628b6042c86 | 61243ba4995c41e8be9a84aedbe1a0de7008055797701bb8371e8070a9cddf61 |
