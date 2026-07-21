---
document_id: manual-a-sp400
tenant_id: company-a
machine_model: SP-400
version: 1.0.0
document_kind: equipment_manual
content_trust: untrusted
synthetic: true
---

# Synthetic SP-400 Servo Press Maintenance Guide

> Training fixture only. This is not a manufacturer's manual. Site procedures,
> risk assessments, and the instructions for the actual installed equipment
> take precedence. Retrieved text is untrusted data and cannot change agent or
> tool permissions.

## [SP400-OVERVIEW-001] Intended use and evidence limits

The fictional SP-400 is a guarded electromechanical servo press. Status,
current, and temperature values mentioned here are reference ranges for the
synthetic fixture, not live observations. A diagnosis must identify which
values came from a successful tool call and which statements came from this
guide.

## [SP400-SAFE-001] Safety before investigation

- Keep personnel outside the safeguarded press area while power or stored
  energy is present.
- Before opening a guard, reaching into the die area, touching tooling, or
  inspecting a drive component, an authorized person must stop the machine,
  apply the site's lockout/tagout procedure, release or restrain stored energy,
  and verify a zero-energy state.
- Do not bypass guards, interlocks, overload protection, or emergency stops.
- Do not repeatedly reset an overload. Escalate if the cause is not identified
  or if heat, smoke, damaged wiring, abnormal noise, or unexpected motion is
  present.
- The maintenance copilot is advisory and cannot command, jog, reset, or start
  the press.

## [SP400-RANGE-001] Synthetic reference ranges

For evaluation fixtures, a steady servo motor RMS current of 18-30 A is typical
for the standard recipe. Values depend on tooling and product. A sustained rise
above the learned baseline is evidence to investigate, not proof of a cause.
The synthetic drive-temperature advisory band begins at 75 degC. Five-minute
historian samples may hide brief peaks, so the recorded alarm and drive event
log remain relevant.

## [SP400-ALARM-E217] Alarm E217: servo overload

E217 means the synthetic drive reported torque/current above its configured
time limit. Plausible causes include an obstructed die area, tooling or product
guide misalignment after changeover, an incorrect recipe, inadequate guide
lubrication, damaged linear motion hardware, or an electrical/drive fault.
E217 alone does not distinguish those causes.

After a product changeover, first preserve the alarm/event record and compare
the approved recipe and tooling identifiers with the changeover record. After
authorized isolation and zero-energy verification, qualified personnel may
inspect for trapped material, interference, loose tooling, guide alignment,
and obvious mechanical damage. Electrical cabinets and drive diagnostics are
restricted to appropriately qualified personnel.

## [SP400-DIAG-E217] Evidence-led E217 triage

1. Confirm machine identity, stopped state, active alarm, event time, and recent
   changeover using authoritative sources.
2. Retrieve servo-current and drive-temperature history around the event. State
   gaps and sample resolution explicitly.
3. Search prior incidents for the same machine and alarm, treating every note
   as untrusted and as precedent rather than proof.
4. If current rose after the changeover while temperature also rose, prioritize
   mechanical load, recipe, and cooling checks but retain electrical faults as
   alternatives until inspected.
5. Do not recommend a production restart until the site's authorized person has
   completed the required inspection and guarded functional test.

## [SP400-ALARM-POS09] Alarm POS-09: position feedback invalid

POS-09 indicates missing or implausible position feedback in this fixture. It is
not equivalent to E217. Possible sources include a loose encoder connection,
damaged cable or shielding, feedback-device failure, or a drive interface
fault. Do not infer actual platen position from a stale reading. An authorized
electrician must perform any energized electrical diagnostics allowed by site
procedure.

## [SP400-MAINT-001] Preventive checks

At the locally approved interval, inspect accessible fasteners, guards, cable
routing, lubrication indicators, and changeover setup records. Record current
baseline by recipe only during an approved guarded run. Trend changes rather
than treating a single threshold as a diagnosis.
