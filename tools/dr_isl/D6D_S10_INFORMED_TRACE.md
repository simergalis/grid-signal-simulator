# D6d — S10 informed-arm unserved-energy trace

## Scope and method

Read-only trace for `S10_mit_supercloud_2021-08-11`, seed 42, using the same
`StudyRunExecutor.run_pair` path for both arms. The captured pair completed
17,280 ticks per arm. A second in-memory instrumented pair reproduced the same
physical identities and run metrics while retaining only selected forecast
snapshots and actual-demand window maxima. Evidence is in
`tools/dr_isl/d6d/D6D_S10_INFORMED_TRACE.json` and
`tools/dr_isl/d6d/D6D_S10_FORECAST_CHECKS.json`. Neither file contains a full
per-tick export.

Baseline: physical identity
`22a109ae31e928518db467fbe3ff90675604ce2e38c0f6ed5551c21aa10d9a3f`,
unserved **5.535769413 MWh**, peak unserved **16.8004944 MW**, **37 starts**,
turbine fuel **7,785.288838529 MMBtu**.

Informed: physical identity
`31500784c695aec403662bb71ccccb0dff6e74d1cb5440197b43251330d380b0`,
unserved **13.940406890 MWh**, peak unserved **31.8004944 MW**, **47 starts**,
turbine fuel **7,428.015428680 MMBtu**. Net unserved increase is
**8.404637477 MWh**. The seed-42 comparison has 8/10 conditions passing and
fails `informed_unserved_energy_no_worse` and
`informed_peak_unserved_no_worse` (`tools/dr_isl/isl25/S10_MCP_ACCEPTANCE_SUMMARY.json`).

## T1 — first divergence and decision path

- First differing field of any kind: tick 1 (5 s), `run_id` and
  `wall_stamp_utc`; these are run metadata, not physical differences.
- First physical/control-output difference: tick 35 (175 s). Baseline has
  `turbine_start_count=1`, turbine-2 OFFLINE, and total turbine fuel
  `15.082988039215687 MMBtu`. Informed has count 2, turbine-2 STARTING, and
  `35.082988039215685 MMBtu`. Demand and turbine output have not yet diverged.
- First different controller action is at simulation time 170 s. Baseline's
  forecast controller returns immediately in baseline mode
  (`P/runtime/turbine_commitment.py:798–802`); its core still has turbine-1's
  start pending. Informed accepts `start turbine-2`, source
  `forecast_commitment`, thermal tier cold, reason “forecast peak exceeds
  synchronized capacity plus BESS allowance over 360s.” Its current forecast
  is 0.278748937 MW and peak is 37.596060937 MW at 530 s; synchronized
  capacity is 15 MW. S10's BESS is 18 MW with a 1 MW anchor reserve, so the
  allowance is 17 MW and the tested threshold is 32 MW. The comparison is
  `37.596060937 > 15 + 17` (`P/runtime/turbine_commitment.py:595–620,
  833–850`; BESS values:
  `P/config/scenarios/S10_mit_supercloud_2021-08-11.json:2162–2166`).
- The same forecast and 15 MW synchronized-capacity value cause accepted
  starts of cold turbines 3 and 4 at 175 s and 180 s. The capacity calculation
  counts SYNCHRONISED turbines only (`P/runtime/turbine_commitment.py:587–593,
  819–825`); the earlier STARTING candidates do not increase that value.
  S10's cold-start duration is 600 s (`P/config/scenarios/S10_mit_supercloud_2021-08-11.json:2302,
  2363, 2424`).
- The first commitment telemetry fields that differ are tick 37 (185 s):
  baseline `commitment_blocked_by="start pending for 'turbine-1'"` and
  `commitment_reason="commit condition met (U=0.019, floor_violated=True)"`;
  informed blocked-by is null and the reason is
  `U=0.019, floor_mw=15.3, total_rated=15.0, commit_sustained=185/30 s, decommit_sustained=0/300 s`.

The workload events are in the tracked S10 scenario: job-00002 starts at
527 s with 2,960 nodes, job-00008 at 13,678 s with 4,902 nodes, and job-00009
at 16,771 s with 4,902 nodes
(`P/config/scenarios/S10_mit_supercloud_2021-08-11.json:15, 132, 150`).
`RunManager.step()` applies due events and evaluates the controller before
physics (`P/runtime/run_manager.py:1900–1906`).

## T2 — informed-worse unserved intervals

There are 27 contiguous intervals in which informed unserved power exceeds
baseline. Positive excess across those intervals totals **11.639698502 MWh**.
Baseline has **3.235061025 MWh** more unserved than informed on other intervals,
leaving the net difference of **8.404637477 MWh**. Every interval is listed
below as `start–end seconds: informed excess MWh`.

```text
16835–18060: 5.674713041
13745–14970: 5.553736240
57195–57345: 0.208415055
54630–54650: 0.027047854
11505–11520: 0.024969916
64445–64460: 0.023186103
35820–35835: 0.021891100
37245–37260: 0.021246971
65455–65465: 0.018651919
55130–55145: 0.011458333
65620–65630: 0.008020189
2635–2640: 0.007291667
80255–80260: 0.007291667
76925–76930: 0.006515658
5590–5600: 0.004166667
45345–45350: 0.004039800
81150–81155: 0.003147656
84090–84095: 0.002937047
56015–56025: 0.002258225
16800–16810: 0.001983872
84610–84615: 0.001620771
80070–80075: 0.001481812
780–790: 0.001388889
4205–4215: 0.000892933
37200–37220: 0.000853013
770–775: 0.000492107
65405–65410: <0.000000001
```

The largest five, with peak conditions and the latest policy start/stop action
before each interval:

1. **16,835–18,060 s** — baseline **2.285588156 MWh**, informed
   **7.960301197 MWh**, excess **5.674713041 MWh**. Both peak at 17,595 s:
   baseline peak **16.8004944 MW**, SoC effectively 0, turbines 0/1/2 each
   synchronized at 15 MW; informed peak **31.8004944 MW**, SoC 0, only
   turbines 0/1 synchronized at 15 MW. Baseline's latest policy action was an
   accepted core stop of turbine-3 at 16,775 s. Informed accepted forecast
   stops of turbine-2 at 16,775 s, turbine-3 at 16,780 s, and turbine-4 at
   16,785 s; the last reason was “forecast peak and minimum support controlled
   stop over 1200s.” Job-00009 starts at 16,771 s. The first informed stop
   completes at the interval's first tick, 16,835 s.
2. **13,745–14,970 s** — baseline **0.001665980 MWh**, informed
   **5.555402220 MWh**, excess **5.553736240 MWh**. Baseline peaks at
   14,835 s: **0.9495056 MW**, SoC **0.1048941**, turbines 0/1/2/3/4 at
   15/14.0505/7.0505/5.25/2.5 MW. Informed peaks at 14,335 s:
   **31.8004944 MW**, SoC 0, turbines 0/1 at 15 MW and turbine-4 synchronized
   at 0 MW (the other units are not on bus). Baseline's latest policy action
   was a core stop of turbine-4 at 13,560 s. Informed accepted forecast stops
   of turbine-3 at 13,680 s and turbine-2 at 13,685 s; its latest policy
   action before the interval was the latter stop. Job-00008 starts at
   13,678 s.
3. **57,195–57,345 s** — baseline **0**, informed **0.208415055 MWh**.
   Baseline peak unserved is 0 at 57,200 s, SoC **0.1104377**, turbines
   0/1/2 at 15 MW. Informed peaks at 57,215 s: **16.8004940 MW**, SoC 0;
   turbines 0/1/4 are synchronized at 15 MW and turbine-3 is synchronized
   at 0 MW. Baseline's latest policy action was a core stop of turbine-3 at
   56,600 s; informed's was a forecast start of turbine-2 at 57,020 s.
4. **54,630–54,650 s** — baseline **0**, informed **0.027047854 MWh**.
   Baseline peak is 0 at 54,635 s, SoC **0.2413863**, all five turbines
   synchronized at 15/8.226/5.25/5.25/5.25 MW. Informed peaks at 54,640 s:
   **9.0240341 MW**, SoC 0, all five are synchronized at
   15/13.226/7.75/5.726/5.25 MW. Latest policy actions were starts of
   turbine-4: baseline core start at 53,105 s; informed forecast start at
   52,100 s.
5. **11,505–11,520 s** — baseline **0**, informed **0.024969916 MWh**.
   Both peak at 11,510 s: baseline peak 0, SoC **0.1473833**, all five
   synchronized at 15/9.3858/5.25/5.25/5.25 MW; informed peak
   **10.3641696 MW**, SoC effectively 0, all five synchronized at
   15/11.8858/7.75/6.2266/5.25 MW. Latest policy actions were starts:
   baseline core start of turbine-3 at 9,930 s; informed forecast start of
   turbine-4 at 9,220 s.

The full per-unit arrays and event records for the five intervals are in the
JSON evidence.

## T3 — mechanism assessment

**Primary mechanism: forecast underprediction followed by accepted forecast
stops (b).** The recorded forecast snapshots show that the imminent job starts
were present in `announced_event_ids`, but their announced workload contribution
was 0 MW at the key stop decisions:

| Decision time | Event | Forecast peak (MW) | Announced workload (MW) | Actual demand then (MW) | Actual next-360-s peak (MW, time) |
|---:|---|---:|---:|---:|---:|
| 13,680 s | job-00008 | 3.803572 | 0 | 0.000095 | 61.800478 at 14,040 s |
| 13,685 s | job-00008 | 3.803573 | 0 | 1.430583 | 61.800482 at 14,045 s |
| 16,775 s | job-00009 | 4.114098 | 0 | 0.000095 | 61.800480 at 17,135 s |
| 16,785 s | job-00009 | 4.122929 | 0 | 4.635053 | 61.800485 at 17,145 s |

The informed controller accepted the stops at those times. Its stop guard
evaluates the supplied forecast profile and refuses only when the post-stop
reserve deficit exceeds its sensitivity (`P/runtime/turbine_commitment.py:658–782,
858–874`). The forecast builder creates that profile from event power at each
sample (`P/runtime/turbine_commitment.py:494–540`); the runtime event-power
estimate is `node_count × profile.rated_kw × site.pue_base / 1000`
(`P/runtime/run_manager.py:1864–1880`). The controller records a forecast miss
when actual demand exceeds its forecast peak by its sensitivity
(`P/runtime/turbine_commitment.py:1444–1450`).

Across the informed run there are **2,000** forecast-miss ticks; the largest
miss is **43.975079649 MW**. These snapshots establish the material underforecast
and its accepted-stop consequence. They do not isolate why the forecast
reports zero announced workload for those announced event IDs; that remains
inside the forecast/event-power data path above and requires a separate
diagnosis to localize further.

The D6b zero-demand reserve-floor knife edge (`P/core/commitment.py:360–369`)
is not the primary cause: the two dominant unserved intervals follow
`forecast_commitment` stop actions, not an informed core decommit. Thermal
state and restart delay affect recovery after stops, but do not explain the
false-low forecast that authorized them. BESS depletion amplifies unserved
energy: informed SoC is zero at all five largest interval peaks; however, the
second-largest episode also has SoC zero in baseline, while baseline has one
more synchronized turbine at the largest peak. There is no defensible additive
MWh allocation among forecast error, unit availability, and BESS depletion
without counterfactual runs. The two largest forecast-stop episodes account
for **11.228449281 MWh** of positive excess, offset elsewhere by baseline-worse
intervals.

For the first event, at 170 s the forecast places 37.596061 MW at 530 s, but
actual demand at 530 s is **0.290061 MW** and reaches **37.607278 MW** at
1,330 s. The controller therefore also uses an inaccurate time profile for
that initial job burst. Its 360 s start horizon is built from the 300 s hot
start look-ahead plus 60 s ramp (`P/runtime/turbine_commitment.py:23–24,
833–850`), while the three selected units are cold with 600 s configured
starts.

## T4 — ten net extra informed starts

Starts per unit are baseline 1/5/15/16 and informed 1/15/15/16 for
turbines 1/2/3/4, respectively: the net increase of 10 is turbine-2's
additional starts, not an exact timestamp-matched causal pairing. The ten
informed count-excess events are:

| Time (s) | Unit | Thermal tier | Source | Reason |
|---:|---|---|---|---|
| 32,945 | turbine-2 | warm | forecast_commitment | Forecast peak exceeds synchronized capacity plus BESS allowance over 360 s |
| 43,186 | turbine-2 | hot | predicted_step_staging | Predicted step delta 15.54888 MW; 45 s lead |
| 46,938 | turbine-2 | hot | predicted_step_staging | Predicted step delta 7.77444 MW; 45 s lead |
| 52,090 | turbine-2 | hot | forecast_commitment | Forecast peak exceeds synchronized capacity plus BESS allowance over 360 s |
| 57,020 | turbine-2 | hot | forecast_commitment | Forecast peak exceeds synchronized capacity plus BESS allowance over 360 s |
| 60,290 | turbine-2 | hot | core_commitment | Reserve floor violated: 30.0 MW < 52.3 MW |
| 71,634 | turbine-2 | hot | predicted_step_staging | Predicted step delta 0.126072 MW; 45 s lead |
| 74,767 | turbine-2 | hot | predicted_step_staging | Predicted step delta 0.126072 MW; 45 s lead |
| 78,099 | turbine-2 | hot | predicted_step_staging | Predicted step delta 0.241638 MW; 45 s lead |
| 81,262 | turbine-2 | hot | predicted_step_staging | Predicted step delta 0.126072 MW; 45 s lead |

Informed also stops units more often: **44 accepted stop commands** and 44
stop-complete transitions versus baseline **34**; informed additionally has
9 refused stop attempts. The log contains 6 accepted and 5 refused
`proposal_decommit` entries; these are counted separately from physical stop
commands. Logs use `action="stop"` for the physical transition, not
`action="decommit"`.

## T5 — verdict

**DEFECT — forecast/event-power path underpredicts imminent S10 workload, then
the informed controller accepts stops based on that forecast.** At the
13,680–13,685 s and 16,775–16,785 s stop decisions, the known event IDs have
0 MW announced contribution and 3.80–4.12 MW forecast peaks, while actual
demand reaches 61.80 MW within 360 s. The immediate code path is
`P/runtime/turbine_commitment.py:529–540` (forecast profile), `:658–782`
(stop-refusal calculation), and `:858–890` (stop decision), using the
event-power callback at `P/runtime/run_manager.py:1864–1880`. No fix or
counterfactual was run; this report ends the D6d diagnosis.
