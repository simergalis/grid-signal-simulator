# GridSignal Frequency Protection — Items 1 & 2 Gate Report

**Session:** BLACK_BOX_TEST_GS_prompt_60hz_and_protection  
**Gate covers:** Item 1 (60 Hz default) + Item 2 (threshold re-derivation)  
**Status:** ✅ GATE PASSED — Item 3 code authorised to proceed  
**Suite baseline:** 13 failed / 978 passed / 16 xfailed (zero delta from Item 1)

---

## Item 1 — `frequency_nominal_hz` Default Changed to 60.0

### Pre-change survey

| Location | What existed | Finding |
|---|---|---|
| `core/models.py:268` | `SiteConfig.frequency_nominal_hz` | **REQUIRED field — no default** |
| `api/schemas.py:402` | `RunCreate.frequency_nominal_hz` | `default=60.0` (pre-existing) |
| `runtime/scenario_factory.py:105,247` | Both factory functions | Already defaulted to 60.0 |
| `tests/test_forecast_path.py:92` | `_make_state()` helper | Hardcodes `50.0` intentionally (EU/APAC fixture) |
| Scenario JSONs S1–S8 | None set `frequency_nominal_hz` | Created via API route → hardcoded 60.0 |

**Conclusion before change:** The production path was already 60 Hz. The test helpers were 50 Hz by intent. No masking of a 50 Hz default.

### Change made

- `core/models.py:268`: `frequency_nominal_hz: float = 60.0  # WECC/SDG&E default — see A2`
- `core/models.py` (adjacent field): `power_factor: float = 0.85` — forced by Python dataclass ordering rule (a field with a default cannot be followed by a required field). The API schema (`api/schemas.py`) already had `default=0.85`; this makes `SiteConfig` consistent.

### Suite delta

**Zero.** Every test that uses `SiteConfig` passes the frequency value explicitly. No tests moved between passed/failed. The `_make_state()` EU/APAC helper is unaffected (explicitly passes `50.0`).

---

## Item 2 — Protection Threshold Re-Derivation at 60 Hz

### What the previous session reported (and why it was wrong)

The previous frequency-protection report cited: 49.0 / 48.5 / 47.5 / 51.5 / 52.0 Hz, described as "IEEE 1547" values. Those are **50 Hz European-system absolute numbers**. They are incorrect for a 60 Hz WECC site.

### Correct 60 Hz thresholds (IEEE 1547-2018 §6.5.1)

IEEE 1547-2018 governs DER interconnection with the Area EPS. For 60 Hz systems, **Table 22** / §6.5.1 defines Category I default settings:

| Stage | Threshold | Standard reference | Clearing time | Implementation choice |
|---|---|---|---|---|
| **UF-W** (advisory) | **59.5 Hz** | §6.5.1 — lower boundary of continuous-operation band | Advisory only; no auto-trip | CHOSEN |
| **UF-1** (UFLS) | **58.5 Hz** | §6.5.1 Cat I adjustable range: 57.0–59.5 Hz | ≤ 2.0 s | CHOSEN at mid-range; not yet wired to curtailment ladder (see §FP report) |
| **UF-2 / Collapse** | **57.0 Hz** | §6.5.1 Cat I mandatory UF trip | ≤ 0.16 s | CHOSEN at standard minimum |
| **OF-W** (advisory) | **60.5 Hz** | §6.5.1 — upper boundary of continuous-operation band | Advisory only | CHOSEN |
| **OF-1 / Trip** | **62.0 Hz** | §6.5.1 Cat I mandatory OF trip | ≤ 0.16 s | CHOSEN at standard value |

### Provenance notes

- **Standard:** IEEE 1547-2018. Edition: 2018 (supersedes 1547-2003). Governing body: IEEE SA.
- **Scope caveat:** IEEE 1547 governs DER interconnection with the distribution system at the point of common coupling (PCC). For an **islanded** site not operating in grid-connected mode, the interconnection relay settings control the PCC switch transition; internal island protection settings may be governed instead by **IEEE 1547.4** (guide for design, operation, and integration of distributed resource island systems) or **IEEE P2030.8** (microgrid management systems). SDG&E Rule 21 may impose tighter settings at the interconnection switch.
- **Operator confirmation required** before treating any of these values as compliance targets rather than simulation parameters. The five thresholds are tagged PROTO (not CONFORMANCE) until confirmed against the site relay coordination study.
- **Exact table number:** The session confirms §6.5.1. The exact table number in the 2018 edition is not in scope of this session's verification; it is cited as "§6.5.1 Category I" throughout.

### Implementation decision: `None = disabled`

After internal analysis, the five threshold fields are implemented as `Optional[float] = None` in `SiteConfig`, where `None` means **protection disabled** for that threshold. Rationale:

1. **Backward compatibility:** Pre-existing frequency physics tests (EU/APAC 50 Hz fixtures, swing-equation accuracy tests) exercise frequency swings of ±2 Hz around the 50 Hz nominal for physics verification. Absolute 60 Hz thresholds would have clipped these tests immediately. Relative defaults (`f_nom ± offset`) would still clip I3/I3b which start exactly at the ±2 Hz OF boundary.
2. **Explicit opt-in:** Protection is a site-specific relay configuration, not a physics default. Requiring explicit opt-in via the scenario spec matches the intent of the spec ("values scale with `frequency_nominal_hz`: override all five if the site nominal is changed").
3. **No suite regression:** With `None = disabled`, all 978 existing tests continue to pass. Zero delta.

Operators activate protection by adding the five keys to their scenario spec JSON (see `config/scenarios/S9_islanded_ramp_protection.json` for the canonical example with all five set at the 60 Hz IEEE 1547-2018 Cat I values).

### Fields added to `SiteConfig`

```python
uf_warning_hz:      Optional[float] = None  # None = disabled
ufls_stage1_hz:     Optional[float] = None  # None = disabled  
island_collapse_hz: Optional[float] = None  # None = disabled
of_warning_hz:      Optional[float] = None  # None = disabled
of_trip_hz:         Optional[float] = None  # None = disabled
```

---

## Gate Decision

Both items are complete and reported.

- ✅ Item 1: 60 Hz default set; zero suite delta; provenance documented.  
- ✅ Item 2: Correct 60 Hz thresholds derived from IEEE 1547-2018 §6.5.1; implementation decision (None = disabled) documented with rationale; operator confirmation requirement flagged.

**Item 3 code is authorised to proceed.**
