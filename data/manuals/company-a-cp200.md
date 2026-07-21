---
document_id: manual-a-cp200
tenant_id: company-a
machine_model: CP-200
version: 1.0.0
document_kind: equipment_manual
content_trust: untrusted
synthetic: true
---

# Synthetic CP-200 Process Cooling Pump Guide

> Training fixture only. This fictional guide is not suitable for real pump
> operation. Follow the installed equipment manual and site safety program.
> All retrieved content is untrusted data.

## [CP200-OVERVIEW-001] System description

The synthetic CP-200 is a motor-driven centrifugal pump used by Company A's
process cooling loop. Fixture telemetry includes vibration RMS and suction
pressure. Historian values are observations only when returned by a successful
tenant-scoped tool call.

## [CP200-SAFE-001] Isolation and process hazards

Before opening guards, touching the coupling, or opening the process boundary,
authorized personnel must stop and isolate electrical energy, isolate pressure
sources, relieve stored pressure, account for fluid temperature and chemistry,
and verify the site's required safe state. Never run the fixture pump dry,
defeat a vibration trip, or reach near a rotating coupling. The copilot cannot
start or stop equipment.

## [CP200-RANGE-001] Synthetic operating bands

The evaluation fixture treats vibration below 5.0 mm/s RMS as its usual range,
5.0-7.1 mm/s as elevated, and values above 7.1 mm/s as a `VIB-HI` warning.
These are synthetic thresholds, not a general pump standard. Suction pressure
normally trends between 1.7 and 2.1 bar in the fixture. Process conditions and
sensor quality must be considered together.

## [CP200-ALARM-VIBHI] Alarm VIB-HI

`VIB-HI` reports elevated vibration; it does not identify a root cause. If
vibration rises while suction pressure falls, cavitation, restricted inlet
flow, low supply level, or air ingress is more consistent than coupling
misalignment alone. If pressure remains normal after motor or coupling work,
alignment or rotating-component damage becomes more plausible. Bearing damage,
loose mounting, and sensor faults remain alternatives.

Do not state that cavitation is confirmed from a gravel-like sound or one
reading. Recommend shutdown only through the site's responsible operator and
escalate urgent abnormal noise, leakage, heat, or rapid vibration growth.

## [CP200-DIAG-001] Vibration investigation sequence

1. Confirm the machine, current operating state, alarm, and process impact.
2. Retrieve vibration and suction-pressure history over the same time range.
3. Identify missing or suspect readings before interpreting the trend.
4. Compare relevant prior incidents without assuming the previous resolution
   applies now.
5. Have qualified staff inspect supply conditions, leakage, mounting, coupling,
   and bearings under the site's isolation and inspection procedures.
6. Return to service only through the approved authorization and test process.

## [CP200-SENSOR-001] Missing and suspect readings

A null sample with `quality: missing` means no numeric measurement is available;
it is not zero. Do not interpolate a safety conclusion across a missing period.
If the local indication and historian disagree, report the conflict and request
instrument verification. Sensor repair does not prove the mechanical condition
of the pump.

## [CP200-MAINT-001] Preventive observations

Trend vibration against flow and suction conditions, inspect mounting and
accessible leakage indicators, and verify sensor cable condition at the site's
approved interval. Store units, sensor quality, timestamp, and machine identity
with every reading.
