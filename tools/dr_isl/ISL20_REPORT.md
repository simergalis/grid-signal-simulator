# IMPL-ISL-20 — read-only diagnosis of carried frequency after D11

Application base: `5fbf3577aee83304f41b9c3a5c1498214987367c`; initial repository HEAD: `4e33116800e1ecd09d2b5bcce8528d48b6ba1099`. `P` below means `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`. Only this report and tools/dr_isl/isl20/*.json are committed. No application, tests, configuration, scenario or catalogue changes; no workflow restart, publishing, deployment or push. No full per-tick export or CSV was created. Source integrity and tooling hashes are in `isl20/INTEGRITY.json` and `isl20/METHOD.json`.

## Answer

The implemented zero-forcing equation does restore frequency through load damping when D_eff > 0, but its time constant is 2H/D_eff, not a fixed short recovery time. D_eff = 0 gives no passive restoration. The separate dispatch droop is explicitly skipped without ufls_stage1_hz or of_trip_hz. The substep governor cascade advances internal valve/power states but no executable consumer applies those terminal states to turbine MW. Grid-forming BESS contributes virtual inertia, not an implemented frequency-to-MW droop loop; diesel supplies no such governor loop either. These statements are traced below to P/core/simulation_core.py:1477–1502,1547–1597,3444–3453,3483–3511,3536–3563; P/core/asset_modules.py:1643–1681; P/core/diesel_fleet.py:180–208. Exact verbatim excerpts and all executable governor-state references are in `isl20/TRACE.json`.

## D1 — source trace

|Mechanism|Reads → writes; does it restore in these runs?|Literal source|
|---|---|---|
|(a) Outer dispatch droop|Reads preceding state._frequency_hz, UFLS1/OF-trip margins, on-bus turbine MW/headroom/minimum; writes _droop_correction_mw and _p_dispatch_droop_mw. No first-stage thresholds → None limit → zero correction. All eight measured cases have no limit.|P/core/simulation_core.py:1504–1597; P/core/droop.py:38–153|
|(b) Governor cascade|Reads instantaneous substep deviation; computes droop MW on rated/pf MVA base; valve lag → fuel lag → per-substep rate limiter; writes _gov_valve_mw/_gov_power_mw only. No actuator consumer outside these self-updates. Comments claiming next-tick terminal-state dispatch are stale relative to executable instantaneous outer droop.|P/core/asset_modules.py:938–944; P/core/simulation_core.py:1463–1466,1522–1524,3536–3563; TRACE.json/executable_governor_field_references|
|(c) GF BESS/VSM|Without on-bus turbines, anchor_mode=vsm uses GF BESS rated/pf MVA and site.vsm_inertia_constant_s. No BESS frequency-error droop or separate VSM damping term feeds swing forcing. BESS response_tau is setpoint tracking, not a frequency sensor/controller.|P/core/simulation_core.py:1484–1502,3444–3453,3500–3511; P/core/asset_modules.py:1643–1681,1733–1758; P/core/models.py:1018–1048|
|(d) Diesel|Coordinator reads gap_mw and timers; DieselModule follows dispatched target/start/unloading state. No frequency/speed/droop input. Diesel is counted for source viability, but turbine-only inertia population excludes it; VSM/fallback branch is used when there is no on-bus turbine.|P/core/diesel_fleet.py:180–208,232–259; P/core/asset_modules.py:1339–1613; P/core/simulation_core.py:1477–1502,3382–3387|
|(e) Load damping|D_eff=(p_cooling_demand_mw/p_demand_mw)*fixed_speed_cooling_fraction*d_motor; zero if demand <= 1e-9. df/dt=[forcing/S_base*f0-D_eff*(f-f0)]/(2H). Only fixed-speed cooling fraction contributes. Numeric ranges below.|P/core/simulation_core.py:3444–3453,3483–3511; P/core/models.py:572–577; isl20/PARAMETER_CATALOGUE.json|
|(f) Frequency → MW paths|Yes, outer bounded turbine droop when first-stage protection is configured, passed downstream as dispatch demand/load command. Renewable over-frequency curtailment also reads prior frequency, requiring OF settings. FC ride-through and UFLS/81U read substep frequency and can trip generation/shed load; these are protection, not primary governors. No unconditional 5-second restoring actuator path.|P/core/simulation_core.py:1356–1385,1547–1597,1665–1740,1887–1945,3513–3534,3565–3669|

### Verbatim key lines (full context in TRACE.json)

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1547–1554`
```python
1547:     try:
1548:         _droop_max_f_err_hz: float | None = _droop_max_freq_error(
1549:             state.site.frequency_nominal_hz, _first_stage_thresholds_hz
1550:         )
1551:     except ValueError:
1552:         # No first-stage protective settings configured for this run — skip droop.
1553:         _droop_max_f_err_hz = None
1554:     if (
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3444–3453`
```python
3444:         # Phase 3: Load damping D_eff (dimensionless, pu/pu).
3445:         # Only fixed-speed motors damp frequency; VFD loads and IT loads do NOT.
3446:         # D_eff ≈ 0.13 at typical 0.45 × 0.30 × 2.5 = 0.3375 MW/MW cooling fraction.
3447:         _d_eff: float = 0.0
3448:         if p_demand_mw > 1e-9:
3449:             _d_eff = (
3450:                 (p_cooling_demand_mw / p_demand_mw)
3451:                 * state.site.fixed_speed_cooling_fraction
3452:                 * state.site.d_motor
3453:             )
```

`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:3536–3563`
```python
3536:             # Phase 4: Advance per-unit bounded governor cascade (valve lag → fuel lag).
3537:             # Governor reads the instantaneous frequency deviation and advances its
3538:             # cascade state. The terminal _gov_power_mw is used by the NEXT outer
3539:             # tick's dispatch correction (outer droop formula). This is a one-outer-tick
3540:             # delay, which is the correct model for governor response to frequency events.
3541:             # Not added to the swing equation forcing within this tick.
3542:             for _t in _on_bus_turbines:
3543:                 _s_i = _t.config.rated_mw / _t.config.power_factor  # MVA base for this unit
3544:                 # Governor demand: droop signal in MW (positive = more output needed).
3545:                 _gov_target = (
3546:                     (-_f_dev / (_t.config.droop_r * _f0)) * _s_i
3547:                     if abs(_f_dev) > _GOVERNOR_DEADBAND_HZ and _t.config.droop_r > 0.0
3548:                     else 0.0
3549:                 )
3550:                 # Valve first-order lag.
3551:                 _alpha_v = 1.0 - math.exp(-_dt_sub / _t.config.valve_actuation_tc_s)
3552:                 _new_valve = _t._gov_valve_mw + (_gov_target - _t._gov_valve_mw) * _alpha_v
3553:                 # Fuel/power first-order lag.
3554:                 _alpha_f = 1.0 - math.exp(-_dt_sub / _t.config.fuel_to_power_tc_s)
3555:                 _new_power = _t._gov_power_mw + (_new_valve - _t._gov_power_mw) * _alpha_f
3556:                 # Rate limiter: max_instantaneous_load_step_mw per sub-step.
3557:                 _step = _new_power - _t._gov_power_mw
3558:                 if abs(_step) > _t.config.max_instantaneous_load_step_mw:
3559:                     _new_power = _t._gov_power_mw + math.copysign(
3560:                         _t.config.max_instantaneous_load_step_mw, _step
3561:                     )
3562:                 _t._gov_valve_mw = _new_valve
3563:                 _t._gov_power_mw = _new_power
```

### Catalogue and defaults
Current seeded library (`P/api/routes/scenarios.py:1474–1490`): **58 scenarios; 0 declare any non-null UF/OF/81U threshold or nonempty UFLS stages**. This is the seeded library, not a query of private customer-created/production records. All entries and 45 scenario-directory files are listed in `isl20/CATALOGUE.json`. The unregistered legacy `P/config/scenarios/S9_islanded_ramp_protection.json:27–31` does declare UF warning 59.5, UFLS1 58.5, collapse 57, OF warning 60.5 and OF trip 62 Hz; it is not a ScenarioSpec catalogue entry.
Defaults are null thresholds and empty staged UFLS: `P/core/models.py:585–630`, `P/runtime/scenario_factory.py:728–765`, `P/api/schemas.py:1990–2058`. Parameter-catalogue example relay/stage settings are not automatically enabled. A grid-tied run nevertheless reports protection_configured=true by the reporting definition, not because the seeded spec has thresholds (`P/core/frequency_reporting.py:14–27`).

## D2 — measured residuals

PROPOSED_HERE analysis epsilon = 1e-9 MW, from the approved D2 comparison and inherited ISL19_REPORT.md:72. The disjoint priority is curtailment-positive, deficit forcing, carried (|public forcing| <= epsilon), then positive forcing without curtailment. The engine frequency_valid flag determines invalidity. Public post-trip forcing is distinguished from actual substep forcing (D11-t). Every baseline non-frequency hash matches its committed D11-t case; each native full-frequency hash is also saved. The eight case JSONs contain every episode, up to ten evenly spaced distinct representative carried ticks, native summary and hashes. Where fewer than ten carried ticks exist, every available tick is listed rather than duplicating rows. An episode ending by relaxation means re-entry into the validity band, not exact restoration to nominal.

|Case / arm|Ticks|Invalid|Curtailment+|Deficit|Carried|Positive/no sink|Hz min / max|
|---|---|---|---|---|---|---|---|
|scenario-h1-k8s-ray-24h / baseline|17280|811|26|52|733|0|17.097716815 / 60.2718768261|
|scenario-h1-k8s-ray-24h / informed|17280|76|0|4|72|0|48.5915675483 / 60.458333516|
|scenario-h2-slurm-24h / baseline|17280|549|54|166|329|0|-239.886266238 / 60.2237056511|
|scenario-h2-slurm-24h / informed|17280|412|51|42|319|0|11.9257761251 / 60.1491765861|
|S10_mit_supercloud_2021-08-11 / app|17280|594|0|476|118|0|-749.690547926 / 60.5459573456|
|scenario-hybrid-ai-100mw-addendum-i / app|120|54|0|10|44|0|-218.7960645 / 60.9795526688|
|demo-islanded-ramp / app|2160|103|0|90|13|0|-127.489611546 / 60|
|scenario-fc100-islanded-zero-hot-v2 / app|264|214|0|207|7|0|-82.804352 / 60|

|Case|D_eff min / max|Carried tau min / p50 / p95 / max (s)|Infinite tau ticks|G=demand ticks / carried|Max |G-demand| MW|Max pure-decay error Hz|
|---|---|---|---|---|---|---|
|scenario-h1-k8s-ray-24h / baseline|0 / 0.602402734893|37.5419996212 / 854.549392631 / 2365.20634921 / 2504.03284656|0|733 / 733|1.7763568394e-15|1.05870867628e-12|
|scenario-h1-k8s-ray-24h / informed|0 / 0.602402734893|474.041360646 / 548.99154703 / 640.766391474 / 640.766392377|0|72 / 72|0|3.41060513165e-13|
|scenario-h2-slurm-24h / baseline|0 / 0.600659399628|13.3187072176 / 797.182647735 / 3032.26253249 / 3142.25226101|0|329 / 329|1.7763568394e-15|6.19593265583e-12|
|scenario-h2-slurm-24h / informed|0 / 0.600659399628|47.7417766578 / 1897.34454669 / 3081.77575034 / 3142.25226101|0|319 / 319|1.7763568394e-15|1.33226762955e-12|
|S10_mit_supercloud_2021-08-11 / app|0 / 0.75|64 / 64 / 88.8178367854 / 39378.6663334|10|118 / 118|0|2.27373675443e-12|
|scenario-hybrid-ai-100mw-addendum-i / app|0 / 0.75|24.4939759934 / 43.398358184 / 89.2131969504 / 173.817507569|14|44 / 44|1.42108547152e-14|3.9221959014e-12|
|demo-islanded-ramp / app|0 / 0.190324098824|63.6504622454 / 64.0003368007 / 64.0013091289 / 64.0015094694|0|13 / 13|0|1.14397380457e-12|
|scenario-fc100-islanded-zero-hot-v2 / app|0 / 0.333333333333|12 / 12 / 12 / 12|0|7 / 7|0|9.80548975349e-13|

Pure-decay prediction uses the exact implemented Euler recurrence: f_end=f0+(f_start-f0)*(1-D_eff*dt_sub/(2H))^n_sub. Its error above is measured only where all integrated raw substeps have zero forcing under the analysis epsilon. Representative observations additionally give the inferred observed tau. This separates true damping-only carried frequency from a zero end-of-tick public value masking a transient/trip.

|Case|Episodes|Duration min / p50 / p95 / max (s)|Episode end reasons|Carried ticks with nonzero substep forcing|
|---|---|---|---|---|
|scenario-h1-k8s-ray-24h / baseline|18|30 / 195 / 360 / 360|{"new_forcing": 12, "relaxation": 6}|0|
|scenario-h1-k8s-ray-24h / informed|1|360 / 360 / 360 / 360|{"relaxation": 1}|0|
|scenario-h2-slurm-24h / baseline|11|40 / 185 / 195 / 195|{"new_forcing": 8, "relaxation": 3}|0|
|scenario-h2-slurm-24h / informed|10|20 / 165 / 278.25 / 285|{"new_forcing": 7, "relaxation": 3}|0|
|S10_mit_supercloud_2021-08-11 / app|7|5 / 45 / 196 / 205|{"relaxation": 7}|0|
|scenario-hybrid-ai-100mw-addendum-i / app|2|60 / 110 / 155 / 160|{"new_forcing": 1, "relaxation": 1}|0|
|demo-islanded-ramp / app|3|5 / 5 / 50 / 55|{"new_forcing": 2, "relaxation": 1}|0|
|scenario-fc100-islanded-zero-hot-v2 / app|1|35 / 35 / 35 / 35|{"relaxation": 1}|0|

### scenario-h1-k8s-ray-24h / baseline
Evidence: `tools/dr_isl/isl20/scenario-h1-k8s-ray-24h_baseline.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|6137–6199|315|deficit_forcing / -1.70228220133|24.826995518 → 31.8567528833|new_forcing|
|6201–6250|250|deficit_forcing / -0.00147637205346|31.9765267045 → 35.4523334173|new_forcing|
|6255–6266|60|curtailment_positive / 0|41.4729035063 → 53.7324519618|relaxation|
|7577–7648|360|deficit_forcing / -2.5|22.748449192 → 37.7998129739|new_forcing|
|7652–7690|195|deficit_forcing / -0.338975482633|37.5168178742 → 41.6657182941|new_forcing|
|7696–7701|30|curtailment_positive / 0|49.6193465139 → 53.9116799359|relaxation|
|9017–9088|360|deficit_forcing / -2.5|20.863248825 → 37.2729545296|new_forcing|
|9092–9130|195|deficit_forcing / -0.542300395667|37.1023026616 → 40.0368846082|new_forcing|
|9135–9146|60|curtailment_positive / 0|45.963418617 → 53.9566567727|relaxation|
|10457–10528|360|deficit_forcing / -2.5|17.584130685 → 39.1258874577|new_forcing|
|10532–10570|195|deficit_forcing / -1.25|37.535255437 → 41.85410936|new_forcing|
|10575–10584|50|curtailment_positive / 0|47.5545799053 → 53.8687246268|relaxation|
|11897–11968|360|deficit_forcing / -2.5|22.9675791912 → 32.2166916313|new_forcing|
|11972–12010|195|deficit_forcing / -0.741633537512|32.0274741746 → 35.0582013798|new_forcing|
|12015–12028|70|curtailment_positive / 0|42.5954679106 → 53.9035516214|relaxation|
|13337–13408|360|deficit_forcing / -2.5|20.0208665347 → 38.6351078405|new_forcing|
|13412–13450|195|deficit_forcing / -1.25|37.1271134492 → 42.6590348112|new_forcing|
|13456–13466|55|curtailment_positive / 0|47.1913069215 → 53.7826144388|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|6137 / 30685|24.826995518|0|4|88.2352941176|0.00883867645934|57.9670683733 / 17.0329316267|29 / 0 / 59|0|905.112890691 / 905.107890682|
|6219 / 31095|33.186656162|0|4|117.647058824|0.00397637542493|58.3283325339 / 41.6716674661|29 / 0 / 59|0|2011.88246709 / 2011.87746709|
|7615 / 38075|32.9928573635|0|4|88.2352941176|0.00835079230135|61.6708586781 / 13.3291413219|29 / 0 / 59|0|957.992931845 / 957.987931836|
|9019 / 45095|21.6687300271|0|4|88.2352941176|0.0170060834509|65.1873962952 / 9.81260370477|29 / 0 / 59|0|470.419895508 / 470.414895491|
|9103 / 45515|38.0430695411|0|4|117.647058824|0.00612552138287|58.6829523998 / 41.3170476002|29 / 0 / 59|0|1306.01127642 / 1306.00627642|
|10499 / 52495|33.2390067273|0|4|88.2352941176|0.0172781662487|63.0874374038 / 11.9125625962|29 / 0 / 59|0|463.012097746 / 463.007097728|
|11899 / 59495|23.4481496895|0|4|88.2352941176|0.0104488979123|58.8700597113 / 16.1299402887|29 / 0 / 59|0|765.630984924 / 765.625984913|
|11983 / 59915|32.6604475794|0|4|117.647058824|0.00332082573572|58.9314433333 / 41.0685566667|29 / 0 / 59|0|2409.03938859 / 2409.03438859|
|13377 / 66885|32.6284204876|0|4|88.2352941176|0.0130706433494|64.3900514057 / 10.6099485943|29 / 0 / 59|0|612.058625284 / 612.053625271|
|13466 / 67330|53.7826144388|0|4|117.647058824|0.122980182386|35 / 65|-23.2465437408 / 52.2465437408 / 6.75345625923|0|65.0511313677 / 65.0461312396|

### scenario-h1-k8s-ray-24h / informed
Evidence: `tools/dr_isl/isl20/scenario-h1-k8s-ray-24h_informed.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|13335–13406|360|deficit_forcing / -1.25|48.7100578498 → 53.9989367593|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|13335 / 66675|48.7100578498|0|4|117.647058824|0.0167046520715|65.2321135613 / 34.7678864387|29 / 0 / 59|0|478.908507988 / 478.90350797|
|13343 / 66715|49.5778439585|0|4|117.647058824|0.0146981934158|64.9749771879 / 35.0250228121|29 / 0 / 59|0|544.284577952 / 544.279577936|
|13351 / 66755|50.3421212707|0|4|117.647058824|0.0153114798814|77.8106257202 / 22.1893742798|16.2427977481 / 12.7572022519 / 46.2427977481|0|522.483787456 / 522.47878744|
|13359 / 66795|51.0626760838|0|4|117.647058824|0.015592889088|68.4607899385 / 31.5392100615|25.25 / 3.75 / 55.25|0|513.054377213 / 513.049377197|
|13367 / 66835|51.7338902619|0|4|117.647058824|0.0156227616912|64.7146018557 / 35.2853981443|29 / 0 / 59|0|512.073355411 / 512.068355395|
|13374 / 66870|52.2430124322|0|4|117.647058824|0.0130705781755|64.3900431463 / 35.6099568537|29 / 0 / 59|0|612.061677193 / 612.056677179|
|13382 / 66910|52.7337506436|0|4|117.647058824|0.0130706849798|64.3900566815 / 35.6099433185|29 / 0 / 59|0|612.056675863 / 612.051675849|
|13390 / 66950|53.1934441666|0|4|117.647058824|0.0130706994342|64.3900585133 / 35.6099414867|29 / 0 / 59|0|612.055999013 / 612.050998999|
|13398 / 66990|53.6123758351|0|4|117.647058824|0.0124850493212|64.3158987986 / 35.6841012014|29 / 0 / 59|0|640.766391401 / 640.761391389|
|13406 / 67030|53.9989367593|0|4|117.647058824|0.0124850493307|64.3158987998 / 35.6841012002|29 / 0 / 59|0|640.766390911 / 640.761390897|

### scenario-h2-slurm-24h / baseline
Evidence: `tools/dr_isl/isl20/scenario-h2-slurm-24h_baseline.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|5883–5890|40|deficit_forcing / -35.4118044938|-137.262444489 → 45.7655006061|new_forcing|
|7284–7322|195|deficit_forcing / -0.936947634459|-140.669109364 → -125.559438336|new_forcing|
|7327–7343|85|curtailment_positive / 0|-93.2352794081 → 20.0367489765|new_forcing|
|8725–8762|190|deficit_forcing / -1.47643215488|-166.456783983 → -129.942298582|new_forcing|
|8767–8802|180|curtailment_positive / 0|-55.246699493 → 53.5889103812|relaxation|
|10164–10202|195|deficit_forcing / -0.915937436903|-139.127987683 → -124.032392928|new_forcing|
|10208–10232|125|curtailment_positive / 0|-53.0939238942 → 43.6166459244|new_forcing|
|11606–11642|185|deficit_forcing / -1.49585346985|-187.455015791 → -136.351431246|new_forcing|
|11647–11683|185|curtailment_positive / 0|-56.9988933846 → 53.7776684559|relaxation|
|13044–13082|195|deficit_forcing / -0.432661436903|-135.837012813 → -122.587231029|new_forcing|
|13088–13101|70|curtailment_positive / 0|-4.14290710134 → 53.9046403409|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|5883 / 29415|-137.262444489|0|4|58.8235294118|0.600656387901|45 / 5|-20.6244746673 / 49.6244746673 / 9.37552533269|0|13.3187628753 / 13.3137622494|
|7312 / 36560|-129.364381841|0|4|88.2352941176|0.00330723991944|63.4401891784 / 11.5598108216|29 / 0 / 59|0|2418.93548544 / 2418.93048544|
|8734 / 43670|-158.277200423|0|4|88.2352941176|0.00741649603946|66.8485114743 / 8.15148852568|29 / 0 / 59|0|1078.67650133 / 1078.67150133|
|8774 / 43870|2.09508977786|-8.881784197e-16|4|88.2352941176|0.125323909886|26.25 / 48.75|-20.0314275887 / 49.0314275887 / 9.96857241133|0|63.83458677 / 63.8295866394|
|10172 / 50860|-136.299757398|0|4|88.2352941176|0.00323982396564|63.4951533527 / 11.5048466473|29 / 0 / 59|0|2469.26996184 / 2469.26496183|
|10213 / 51065|-14.7252800894|0|4|88.2352941176|0.133783627967|26.25 / 48.75|-22.963765502 / 51.963765502 / 7.03623449799|0|59.7980494443 / 59.7930493049|
|11623 / 58115|-161.669857685|0|4|88.2352941176|0.00999558227448|69.7752251259 / 5.2247748741|29 / 0 / 59|0|800.353574241 / 800.348574231|
|11663 / 58315|35.3719722091|1.7763568394e-15|4|88.2352941176|0.160286807666|26.25 / 48.75|-19.9299726571 / 48.9299726571 / 10.0700273429|0|49.9105329784 / 49.9055328114|
|13060 / 65300|-130.718939347|0|4|88.2352941176|0.00261130224132|63.9168823642 / 11.0831176358|29 / 0 / 59|0|3063.60553498 / 3063.60053497|
|13101 / 65505|53.9046403409|8.881784197e-16|4|88.2352941176|0.290958120836|26.25 / 48.75|-23.6752349216 / 52.6752349216 / 6.32476507841|0|27.4953659207 / 27.4903656176|

### scenario-h2-slurm-24h / informed
Evidence: `tools/dr_isl/isl20/scenario-h2-slurm-24h_informed.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|5834–5843|50|deficit_forcing / -1.25|37.5890865499 → 39.2220622414|new_forcing|
|5848–5862|75|deficit_forcing / -1.41660010587|42.7069590838 → 53.9957299316|relaxation|
|7271–7322|260|deficit_forcing / -0.935165637481|12.0240185315 → 16.8014648792|new_forcing|
|7329–7332|20|curtailment_positive / 0|27.1456957485 → 30.6899054965|new_forcing|
|8712–8762|255|deficit_forcing / -1.25072574675|14.6038583054 → 23.2944273625|new_forcing|
|8769–8781|65|curtailment_positive / 0|41.9670843075 → 53.5968584132|relaxation|
|10146–10202|285|deficit_forcing / -6.65186516921|44.1578330816 → 45.7803683433|new_forcing|
|11589–11642|270|deficit_forcing / -2.5|18.1235151867 → 30.1340737199|new_forcing|
|11649–11657|45|curtailment_positive / 0|45.7108509266 → 53.6708605576|relaxation|
|13029–13082|270|deficit_forcing / -1.25|25.0984699175 → 28.2455875705|new_forcing|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|5834 / 29170|37.5890865499|0|4|117.647058824|0.0114771349051|70.1281894713 / 29.8718105287|29 / 0 / 59|0|697.038073192 / 697.03307318|
|7281 / 36405|12.9955262177|0|4|117.647058824|0.00327329838749|63.4359874248 / 36.5640125752|29 / 0 / 59|0|2444.0179455 / 2444.0129455|
|7317 / 36585|16.3648832379|0|4|117.647058824|0.00324292058036|66.5242241824 / 33.4757758176|27.75 / 1.25 / 57.75|0|2466.91209413 / 2466.90709413|
|8737 / 43685|18.4216244056|0|4|117.647058824|0.00771554132467|78.75 / 21.25|15.099007191 / 13.900992809 / 45.099007191|0|1036.86827189 / 1036.86327188|
|8778 / 43890|51.8945003656|-8.881784197e-16|4|117.647058824|0.12565278564|35 / 65|-28.7781519471 / 57.7781519471 / 1.22184805291|0|63.6675101091 / 63.6625099782|
|10178 / 50890|45.0210129027|0|4|117.647058824|0.00338464607514|77.5 / 22.5|14.5276279329 / 14.4723720671 / 44.5276279329|0|2363.61493119 / 2363.60993119|
|11599 / 57995|20.6694167127|0|4|117.647058824|0.00926911211419|68.7902294675 / 31.2097705325|29 / 0 / 59|0|863.081587691 / 863.076587681|
|11634 / 58170|28.5330402436|0|4|117.647058824|0.0100924361703|68.8990444767 / 31.1009555233|29 / 0 / 59|0|792.672835874 / 792.667835863|
|13047 / 65235|26.1098907318|0|4|117.647058824|0.0026567091897|62.9379900039 / 37.0620099961|29 / 0 / 59|0|3011.24414784 / 3011.23914784|
|13082 / 65410|28.2455875705|0|4|117.647058824|0.00673181160255|63.4420566796 / 36.5579433204|29 / 0 / 59|0|1188.38738698 / 1188.38238697|

### S10_mit_supercloud_2021-08-11 / app
Evidence: `tools/dr_isl/isl20/S10_mit_supercloud_2021-08-11_app.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|1923–1944|110|deficit_forcing / -2.14689752|49.6114601657 → 53.9809894249|relaxation|
|2391–2391|5|deficit_forcing / -2.25|53.9787014477 → 53.9787014477|relaxation|
|3649–3657|45|deficit_forcing / -1.5504944|48.3633238088 → 53.7716402369|relaxation|
|6811–6851|205|deficit_forcing / -2.3004944|-86.1741796451 → 53.5791227232|relaxation|
|10554–10588|175|deficit_forcing / -1.47581978357|-32.417531183 → 53.5125990088|relaxation|
|11614–11622|45|deficit_forcing / -1.5504944|48.3896835661 → 53.7857489093|relaxation|
|12920–12920|5|deficit_forcing / -3.14707384167|53.6656008179 → 53.6656008179|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|1923 / 9615|49.6114601657|0|4|52.9411764706|0|30.613192 / 14.386808|17 / 0 / 35|0|n/a / n/a|
|1936 / 9680|49.994134596|0|4|52.9411764706|0.0384019316521|33.1826741645 / 11.8173258355|17 / 0 / 35|0|208.322853977 / 208.317853937|
|3652 / 18260|50.7948000302|0|4|88.2352941176|0.125|61.8004944 / 13.1995056|0 / 0 / 18|0|64 / 63.9949998698|
|6818 / 34090|-24.5955100783|0|4|52.9411764706|0.125|44.8004944 / 0.1995056|17 / 0 / 35|0|64 / 63.9949998698|
|6831 / 34155|29.3639678069|0|4|52.9411764706|0.125|44.8004944 / 0.1995056|17 / 0 / 35|0|64 / 63.9949998698|
|6844 / 34220|48.9052448804|0|4|52.9411764706|0.125|44.8004944 / 0.1995056|17 / 0 / 35|0|64 / 63.9949998698|
|10559 / 52795|-2.53104761173|0|4|52.9411764706|0.124999630739|38.9759349284 / 6.02406507155|17 / 0 / 35|0|64.0001890621 / 63.9951889319|
|10572 / 52860|37.354534745|0|4|52.9411764706|0.124999985682|38.9759667177 / 6.02403328232|17 / 0 / 35|0|64.0000073307 / 63.9950072005|
|10585 / 52925|51.7990065554|0|4|52.9411764706|0.124999999445|38.9759679503 / 6.02403204972|17 / 0 / 35|0|64.0000002842 / 63.995000154|
|12920 / 64600|53.6656008179|0|4|88.2352941176|0.107142857142|54.4210799999 / 20.5789200001|0 / 0 / 24.1750232193|0|74.6666666671 / 74.6616665555|

### scenario-hybrid-ai-100mw-addendum-i / app
Evidence: `tools/dr_isl/isl20/scenario-hybrid-ai-100mw-addendum-i_app.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|6–37|160|deficit_forcing / -1.4310648|-218.7960645 → 10.7664019559|new_forcing|
|43–54|60|deficit_forcing / -4.04378251936|2.15680689008 → 53.7088902765|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|6 / 30|-218.7960645|0|2|17.6470588235|0|0 / 0|14 / 0 / 29|18.3935648|n/a / n/a|
|11 / 55|-218.7960645|0|2|17.6470588235|0|0 / 0|0 / 14 / 15|31.8935648|n/a / n/a|
|16 / 80|-218.7960645|0|2|17.6470588235|0|0 / 0|0 / 14 / 15|31.3935648|n/a / n/a|
|20 / 100|-210.890297722|0|2|17.6470588235|0.0230126415684|0 / 0|2.66104470877 / 11.3389552912 / 17.6610447088|65|173.817507569 / 173.812507521|
|25 / 125|-126.320441638|0|2|17.6470588235|0.0750383674513|0 / 0|11.384461879 / 2.61553812102 / 26.384461879|65|53.3060637626 / 53.3010636063|
|30 / 150|-49.8433669945|0|2|17.6470588235|0.0885992474148|0 / 0|13.5270151417 / 0.472984858317 / 28.5270151417|65|45.1471103504 / 45.1421101658|
|35 / 175|-2.09870825225|0|2|17.6470588235|0.0923846547695|0 / 0|13.7841193274 / 0.215880672593 / 28.7841193274|65|43.2972338315 / 43.292233639|
|44 / 220|12.4813676945|0|2|17.6470588235|0.157260189675|0 / 0|0 / 14 / 15|50.6126421674|25.4355537041 / 25.4305533764|
|49 / 245|42.5824063305|1.42108547152e-14|2|17.6470588235|0.161969873971|0 / 0|0 / 14 / 15|50.9537153877|24.6959505612 / 24.6909502237|
|54 / 270|53.7088902765|0|2|17.6470588235|0.163305459313|0 / 0|0 / 14 / 15|50.6946868998|24.4939759934 / 24.4889756531|

### demo-islanded-ramp / app
Evidence: `tools/dr_isl/isl20/demo-islanded-ramp_app.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|198–198|5|deficit_forcing / -2.36921571366|-76.3449441075 → -76.3449441075|new_forcing|
|204–204|5|deficit_forcing / -0.271439073336|-25.1734566659 → -25.1734566659|new_forcing|
|228–238|55|deficit_forcing / -0.168202656024|46.21585033 → 53.6895040455|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|198 / 990|-76.3449441075|0|4|52.9411764706|0.125469985518|44.9617934854 / 0.0382065146456|17 / 0 / 35|0|63.7602687766 / 63.7552686459|
|204 / 1020|-25.1734566659|0|4|52.9411764706|0.125686439937|44.9884767443 / 0.0115232557464|17 / 0 / 35|0|63.6504622454 / 63.6454621145|
|229 / 1145|47.2518050571|0|4|52.9411764706|0.12499770401|44.903637488 / 0.0963625120046|17 / 0 / 35|0|64.0011755686 / 63.9961754384|
|230 / 1150|48.2099058267|0|4|52.9411764706|0.124998211882|44.9036999794 / 0.0963000205704|17 / 0 / 35|0|64.0009155293 / 63.9959153991|
|231 / 1155|49.096002464|0|4|52.9411764706|0.124998607414|44.9037486478 / 0.0962513521925|17 / 0 / 35|0|64.0007130122 / 63.995712882|
|233 / 1165|50.6734192737|0|4|52.9411764706|0.124999155354|44.9038160696 / 0.0961839303584|17 / 0 / 35|0|64.0004324615 / 63.9954323313|
|234 / 1170|51.3743719893|0|4|52.9411764706|0.12499934219|44.903839059 / 0.0961609410445|17 / 0 / 35|0|64.0003368007 / 63.9953366705|
|235 / 1175|52.0226443115|0|4|52.9411764706|0.124999487697|44.9038569631 / 0.0961430369488|17 / 0 / 35|0|64.0002623003 / 63.9952621701|
|237 / 1185|53.1766863621|0|4|52.9411764706|0.124999689272|44.9038817662 / 0.0961182338422|17 / 0 / 35|0|64.0001590929 / 63.9951589627|
|238 / 1190|53.6895040455|0|4|52.9411764706|0.124999758005|44.9038902235 / 0.0961097765462|17 / 0 / 35|0|64.0001239016 / 63.9951237714|

### scenario-fc100-islanded-zero-hot-v2 / app
Evidence: `tools/dr_isl/isl20/scenario-fc100-islanded-zero-hot-v2_app.json`.
|Episode first–last tick|Seconds|Predecessor class / forcing MW|Hz first → last|End reason|
|---|---|---|---|---|
|253–259|35|deficit_forcing / -21.00064|-34.1260791703 → 52.2817094698|relaxation|

|Tick / sim s|Hz|Forcing MW|H s|S_base MVA|D_eff|GT / raise headroom MW|BESS / raise / lower headroom MW|Diesel MW|Predicted / observed tau s|
|---|---|---|---|---|---|---|---|---|---|
|253 / 1265|-34.1260791703|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|254 / 1270|-2.04095782717|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|255 / 1275|19.1071838746|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|256 / 1280|33.046476566|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|257 / 1285|42.2342285432|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|258 / 1290|48.2901159016|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|
|259 / 1295|52.2817094698|0|2|70.5882352941|0.333333333333|0 / 0|30.00024 / 28.99976 / 90.00024|0|12 / 11.9949993053|

## D3 — process-only counterfactual, not a fix

PROPOSED_HERE R=0.05, requested by Lloyd; citation: NERC Reliability Guideline: Primary Frequency Control, September 2023, Chapter 4/Table 4.2, https://www.nerc.com/globalassets/who-we-are/standing-committees/rstc/rs/primary_frequency_control_reliability_guideline_v_4.0_clean_v3---dr.pdf. The same 5% is a measurement surrogate for GF BESS, not a claim that this guideline calibrates this BESS.
The substep-only response is sum of per-unit clamp[-lower margin, raise headroom] of -(f-f0)/(f0*R)*rated MW, for on-bus synchronous units and nontripped GF BESS. Instantaneous physical headroom, anchor reserve and AC energy/charge-space limits are used; no new SoC debit, fuel use, mechanical output or ledger source is introduced. These limits are not funded normal-dispatch reserve permissions or a validated dynamic governor model. Exact procedure and bounds are in METHOD.json.
All eight process-only assays preserve real unit MW, SoC, served/unserved and curtailment; seven also have identical full non-frequency hashes. For fc100-zero, only fuel_cell_ride_through_status differs on 9 ticks; a separate full-field comparison verifies that the ledger is identical. At tick 255 its reported region changes from trip_under_56_5hz to continuous, without changing real output. Evidence: FC_ZERO_COUNTERFACTUAL_DIFFERENCES.json. Native frequency-sensitive code remains enabled; no unit-output or ledger write is introduced.

|Case|Invalid fraction before → after|Hz min/max before → after|Implied integral |dP| MWh|Share of served energy (fraction)|Remaining invalid classes|Only deficit?|MW/ledger unchanged?|
|---|---|---|---|---|---|---|---|
|scenario-h1-k8s-ray-24h / baseline|0.0469328703704 → 0|17.097716815,60.2718768261 → 58.600492262,60.0257058675|0.907611642985|0.0024677996565|{"curtailment_positive": 0, "deficit_forcing": 0, "carried": 0, "positive_forcing_no_curtailment": 0}|True|True|
|scenario-h1-k8s-ray-24h / informed|0.00439814814815 → 0|48.5915675483,60.458333516 → 59.3782069795,60.0170779536|0.1445556629|0.000392225987877|{"curtailment_positive": 0, "deficit_forcing": 0, "carried": 0, "positive_forcing_no_curtailment": 0}|True|True|
|scenario-h2-slurm-24h / baseline|0.0317708333333 → 0.0162037037037|-239.886266238,60.2237056511 → -231.966301444,60.0267569262|3.46599342523|0.0249443645759|{"curtailment_positive": 0, "deficit_forcing": 163, "carried": 117, "positive_forcing_no_curtailment": 0}|False|True|
|scenario-h2-slurm-24h / informed|0.0238425925926 → 0|11.9257761251,60.1491765861 → 58.7294952896,60.0273454832|0.875438502647|0.00611764374623|{"curtailment_positive": 0, "deficit_forcing": 0, "carried": 0, "positive_forcing_no_curtailment": 0}|True|True|
|S10_mit_supercloud_2021-08-11 / app|0.034375 → 0.0288194444444|-749.690547926,60.5459573456 → -749.251121877,60.5459573456|0.788211285803|0.00128699189821|{"curtailment_positive": 0, "deficit_forcing": 454, "carried": 44, "positive_forcing_no_curtailment": 0}|False|True|
|scenario-hybrid-ai-100mw-addendum-i / app|0.45 → 0.1|-218.7960645,60.9795526688 → -203.3906016,60.9813866015|0.104972551023|0.00683185981341|{"curtailment_positive": 0, "deficit_forcing": 9, "carried": 3, "positive_forcing_no_curtailment": 0}|False|True|
|demo-islanded-ramp / app|0.0476851851852 → 0.0462962962963|-127.489611546,60 → -126.261954002,60|0.0815078225142|0.000578349405011|{"curtailment_positive": 0, "deficit_forcing": 90, "carried": 10, "positive_forcing_no_curtailment": 0}|False|True|
|scenario-fc100-islanded-zero-hot-v2 / app|0.810606060606 → 0.791666666667|-82.804352,60 → -82.804352,60|0.103891979851|0.00485962208768|{"curtailment_positive": 0, "deficit_forcing": 207, "carried": 2, "positive_forcing_no_curtailment": 0}|False|True|

The implied response energy is not measured delivered energy. In a physical implementation it must be supplied and fuelled/debited by actual units and included in accounting; it cannot be counted as a free correction to forcing. No certification inference follows from these counterfactual Hz values.

## D4 — classification, scope and direction (no fix applied)

**Classification:** the damping-only carried tail is the correct mathematical output of the implemented unprotected model, not numerical instability or residual repeated integration of the D11 sink. It is also a primary-response model-coverage gap for any claim of closed-loop islanded regulation: the executable actuator droop is conditional on protection configuration, GF BESS/diesel do not supply a primary frequency-response loop, and the cascade terminal-state comments do not describe an actual actuator consumer. Separately, the cascade is rate-limited but not capped to unit headroom at its terminal state; it is not delivered MW (P/core/simulation_core.py:3544–3563). Recorded governor states and real MW are preserved in the representative-tick JSONs; do not wire that state into forcing unbounded.

**Scope evidence:** the supplied Forecast Engine FS explicitly states at `attached_assets/GridSignal-Forecast-Engine-Functional-Spec_v2.5_1785353484165.md:460` that genset-anchor droop dynamics are outside its Section 7 ramp-rate model and recorded as PX-2. Its line 1603 explicitly lists the genset-anchored islanded droop model as an open item. Later code implements bounded turbine droop when protection is configured (P/core/droop.py:79–122; simulation_core.py:1547–1597). `docs/addendum-h-phase2a-change-record.md:38–64` documents D11 surplus ordering and adds no unconditional governor. A standalone authoritative Addendum G2 §G2.6 or full Addendum H primary-response scope text was not located among the available source documents; source code cites §G2.6.2 for source viability, not a delivered governor loop. Do not infer a broader contractual scope from that comment. TRACE.json includes the available exact FS/addendum excerpts.

Verbatim scope, `attached_assets/GridSignal-Forecast-Engine-Functional-Spec_v2.5_1785353484165.md:460`:
> - **Where the anchor is a genset, the constraint moves.** A genset anchor is governed by its droop response and inertia rather than by transfer timing, and it is the droop dynamics that bound how fast load can be added. This is outside the ramp-rate model in Section 7 and is recorded as PX-2.

Verbatim open item, `attached_assets/GridSignal-Forecast-Engine-Functional-Spec_v2.5_1785353484165.md:1603`:
> - **PX-2 — Anchor droop dynamics.** Where a genset is the grid-forming anchor, its droop and inertia response bounds how quickly load can be added — a constraint the r_asset ramp model in Section 7 does not express. Section 7.1.2 records the consequence; the model does not yet exist.

**Fix direction (design only):** retain one physical source-allocation/control implementation, distinguish the scheduled load-following target from delivered primary-frequency response, and apply any validated turbine/diesel governor or GF-BESS droop through the units’ actual bounded output or a sub-tick unit-response model. Integrate its real energy/fuel/SoC effects and keep the ledger consistent, rather than injecting unbooked MW into swing forcing. Separate primary-response availability from the presence of protection settings without inventing an unbounded alternative; define limits, reserve permissions and any secondary/isochronous restoration explicitly. A saturated fleet cannot restore a sustained deficit by droop alone: retain explicit shedding/unserved/protection behavior and do not erase D7 shortfall forcing merely by relabelling it served. This paragraph is not an implemented or approved fix.

### Deficit forcing and D7

|Case|Invalid deficit ticks|With booked unserved > epsilon|Without booked unserved|Unserved on these ticks MWh|
|---|---|---|---|---|
|scenario-h1-k8s-ray-24h / baseline|52|52|0|0.815865914796|
|scenario-h1-k8s-ray-24h / informed|4|4|0|0.0512009988409|
|scenario-h2-slurm-24h / baseline|166|166|0|5.00559112395|
|scenario-h2-slurm-24h / informed|42|42|0|0.853235930264|
|S10_mit_supercloud_2021-08-11 / app|476|476|0|8.30255499523|
|scenario-hybrid-ai-100mw-addendum-i / app|10|10|0|0.110409349101|
|demo-islanded-ramp / app|90|90|0|0.777380045796|
|scenario-fc100-islanded-zero-hot-v2 / app|207|207|0|6.03733000433|

D7 reconciles served/unserved after frequency integration (`P/core/simulation_core.py:3708–3729`); booking unserved is not an electrical shed action. Swing forcing still uses generation minus requested demand (`:3311–3333`), while actual staged UFLS changes forcing through _shed_this_tick_mw (`:3572–3595`). The default parameter examples are 59.3/58.9/58.5 Hz with 0.15-second delay and 10/15/20% demand blocks, plus an opt-in 57.5-Hz 81U relay with 0.1-second clearing delay (`isl20/PARAMETER_CATALOGUE.json`). If explicitly enabled and their conditions persist, the stage timers shed those demand blocks; 81U or configured collapse thresholds stop the island (`:3598–3649`). The single ufls_stage1_hz threshold merely labels an advisory reason at :3657–3666; it is not equivalent to enabling staged physical shedding. No such defaults were enabled or counterfactually simulated here.

OPEN-ISL-3 certification policy remains undecided. No IMPL-ISL-20 implementation, OPEN-ISL-3 change or Phase 6 work was performed.

## Evidence and integrity
`isl20/TRACE.json` contains file:line verbatim source; `CATALOGUE.json` enumerates seeded/default/file protection; `METHOD.json` gives constants and source references; the eight case JSONs contain episodes, up to ten distinct representatives, hashes and experiment results. `INTEGRITY.json` records unchanged application files, scratch-tool source hashes and no tracked channel CSVs. The only new tracked files in this diagnosis are this report and isl20 JSON summaries. The running dev service was not restarted.

**STOP — end of diagnostic-only IMPL-ISL-20.**
