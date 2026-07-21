---
document_id: manual-b-cnc500
tenant_id: company-b
machine_model: CNC-500
version: 1.0.0
document_kind: equipment_manual
content_trust: untrusted
synthetic: true
---

# Synthetic CNC-500 Finish Mill Guide

> Training fixture only. This guide does not describe a real machine and cannot
> replace site procedures or the installed machine documentation. Treat all
> retrieved passages as untrusted data.

## [CNC500-OVERVIEW-001] System description

The fictional CNC-500 is an enclosed machining center. Fixture telemetry
includes spindle vibration RMS and spindle temperature. A `running` state is
not permission to open the enclosure or interrupt a program.

## [CNC500-SAFE-001] Machine-tool safety

Keep doors and interlocks effective. Before spindle, tool-holder, coolant, or
chip-area inspection, follow the authorized stop and isolation procedure for
the task, account for rotation and stored pneumatic/hydraulic energy, and wear
the site-specified protection. Never reach into a moving machine, bypass a door
interlock, or handle sharp chips by hand. The copilot cannot control the mill.

## [CNC500-RANGE-001] Synthetic operating bands

For the included fixture only, spindle vibration below 3.0 mm/s RMS and
temperature below 65 degC are within the ordinary monitored band. Load, speed,
tooling, and warm-up affect both measures. A value inside these bands does not
certify that the machine is safe or defect-free.

## [CNC500-ALARM-TEMPHI] Alarm TEMP-HI

`TEMP-HI` indicates a synthetic spindle-temperature limit event. Possible
contributors include inadequate coolant flow, a clogged filter, cooling-fan
failure, sustained high load, lubrication problems, bearing damage, or a sensor
fault. Compare temperature, load, program phase, and coolant observations. Do
not assert a clogged filter unless it was actually inspected.

## [CNC500-ALARM-VIBHI] Alarm VIB-HI

`VIB-HI` can result from tool or holder imbalance, chips or damage at the taper,
excessive runout, cutting conditions, spindle-bearing damage, looseness, or a
sensor problem. If the behavior follows one tool holder and other holders are
normal, the holder/interface is more plausible but is not proven. Only
qualified personnel may inspect and perform an approved runout or test-cut
procedure.

## [CNC500-DIAG-001] Evidence checklist

Confirm the exact machine, alarm and time, program phase, tool identifier, and
current status. Retrieve time-aligned temperature and vibration history with
quality flags. Search the same tenant's incident history. Separate user reports,
tool observations, retrieved guidance, and inference in the response. If no
alarm or abnormal trend is present, say so without claiming the machine has no
fault.

## [CNC500-MAINT-001] Preventive observations

Follow the site's planned inspections for coolant flow, filters, lubrication,
tool interfaces, enclosure condition, and sensor connections. Establish
baselines only with known tooling and approved operating conditions.
