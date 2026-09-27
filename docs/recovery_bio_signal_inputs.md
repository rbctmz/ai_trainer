# Recovery Bio Signal Inputs

Status: observational collection only. These fields are not used by readiness
fusion until a separate signal-value review proves they add information beyond
HRV, RHR, sleep, training status, and TSB.

## Availability Check

Local package inspection on 2026-07-04 showed:

- `garminconnect.Garmin.get_respiration_data(cdate)` is available.
- `garminconnect.Garmin.get_spo2_data(cdate)` is available.
- No skin/wrist temperature method is exposed by the installed
  `garminconnect` class or by the current `garth` package surface.

Implementation therefore collects respiration and SpO2 when the authenticated
Garmin account/device returns data. Skin temperature is represented as a
nullable `daily_health.skin_temperature_avg` field and an optional client hook,
but no stable Garmin source is assumed.

## Storage Contract

`daily_health` now accepts these nullable observational fields:

- `respiration_avg`
- `respiration_min`
- `respiration_max`
- `spo2_avg`
- `spo2_min`
- `skin_temperature_avg`

The sync path stores the values when Garmin returns them. Missing values mean
either the device/account does not expose that metric, the endpoint returned no
data for that day, or the current client library has no stable source.

## Readiness Guardrail

These fields must not influence `models.signals_engine`, readiness scoring, or
planning decisions until a later issue evaluates:

- coverage across real synced days,
- correlation with HRV/RHR/sleep readiness,
- false-positive risk for illness/recovery alerts,
- whether the signal changes decisions in a way the user can inspect.

## Submaximal Fatigue Tests — Intervals.icu beta

Status: research candidate / observational only.

Intervals.icu's beta feature detects repeated submaximal efforts at a fixed
power or pace and exposes heart-rate response, heart-rate recovery, optional
RPE, and time-to-exhaustion (TTE) context. Detected activities receive the
`#SFT` tag and existing activities can be re-analysed. The provider post does
not yet publish the detection algorithm, quality thresholds, HR-recovery
window, or a stable API contract:

- Source: [Intervals.icu Submaximal Fatigue Testing (beta)](https://forum.intervals.icu/t/submaximal-fatigue-testing-beta/132525)
- Protocol context: [Science to Sport — Submaximal Fatigue Test](https://www.sciencetosport.com/how-to-perform-a-sub-maximal-fatigue-test/)
- Evidence context: [PubMed systematic review](https://pubmed.ncbi.nlm.nih.gov/27701968/)

### Non-goals

- Do not add SFT directly to the readiness score.
- Do not mutate the plan or create a recovery proposal from one test.
- Do not interpret one HR-recovery value as a diagnosis of fatigue,
  overreaching, or illness.
- Do not treat the beta's inferred detection behavior as a provider contract.

### Promotion gate

Before SFT can influence readiness, Coach, or planning decisions, verify:

- a stable provider contract and explicit field provenance;
- a constant, comparable target across tests, including protection against
  FTP-driven target drift;
- target adherence, HR data quality, recovery-window definition, RPE scale,
  TTE, and relevant confounders;
- a personal baseline built from repeated comparable tests;
- false-detection, re-analysis idempotency, missing-data, and multi-sport
  checks;
- that any resulting decision is inspectable and does not bypass existing
  freshness and intervention gates.
