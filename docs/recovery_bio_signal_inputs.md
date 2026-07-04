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
