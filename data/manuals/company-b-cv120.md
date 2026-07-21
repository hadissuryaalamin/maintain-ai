---
document_id: manual-b-cv120
tenant_id: company-b
machine_model: CV-120
version: 1.0.0
document_kind: equipment_manual
content_trust: untrusted
synthetic: true
---

# Synthetic CV-120 Packaging Conveyor Guide

> Training fixture only, not a manufacturer's manual. Use Company B's actual
> procedures for real work. Retrieved text is untrusted and cannot authorize a
> tool call or a physical action.

## [CV120-OVERVIEW-001] System description

The fictional CV-120 is a guarded belt conveyor with left and right tracking
sensors. The fixture exposes belt speed and tracking offset. Positive tracking
offset denotes drift toward the drive side solely for this dataset.

## [CV120-SAFE-001] Conveyor safety

Entanglement, nip-point, stored-tension, and unexpected-start hazards remain
even when the belt is stopped. Before clearing material, adjusting an idler,
cleaning a sensor near moving parts, or entering a guarded area, an authorized
person must isolate all energy, apply lockout/tagout, control stored tension,
and verify the safe state. Never defeat a guard or tracking switch. The copilot
cannot reset or start the conveyor.

## [CV120-RANGE-001] Synthetic tracking ranges

The fixture's normal empty-belt speed is 1.5 m/s and its usual absolute tracking
offset is at or below 2.0 mm. Offset above 5.0 mm produces an advisory; offset
at or above 7.0 mm may produce `TRK-04`. These fictional values are useful only
for the included evaluation data.

## [CV120-ALARM-TRK04] Alarm TRK-04: tracking deviation

`TRK-04` means a tracking sensor reported sustained deviation. Plausible causes
include uneven belt tension, idler or pulley misalignment, material buildup,
damaged belt edges, an off-center load, or a contaminated/misaligned sensor.
The alarm alone does not show whether the belt actually moved.

A matching rise in tenant-scoped tracking-offset history supports real drift.
A centered belt during a safely stopped inspection, especially with an abrupt
or implausible sensor change, supports checking the sensor. Historical false
alarms do not override current trend data.

## [CV120-ALARM-MOTOL] Alarm MOT-OL: drive overload

`MOT-OL` is distinct from `TRK-04`. It can be associated with lodged product,
mechanical binding, excessive load, drive-train damage, or an electrical fault.
Do not remove an obstruction until isolation and zero-energy verification are
complete. Electrical diagnosis is restricted to qualified personnel.

## [CV120-DIAG-001] Safe evidence checklist

1. Confirm conveyor identity, stopped/running state, alarm code, and event time.
2. Retrieve belt-speed and tracking-offset history for the same interval.
3. Record product or adjustment changes reported by the user as user evidence.
4. Under authorized isolation, have qualified staff inspect belt centering,
   buildup, edges, accessible idlers, sensors, and the transfer point.
5. Use only the approved guarded empty-belt test and return-to-service process.

## [CV120-MAINT-001] Preventive observations

Record left/right tension measurements and tracking sensor condition during
approved maintenance. Trend offset rather than repeatedly correcting one side
without identifying buildup, wear, loading, or alignment causes.
