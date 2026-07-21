# Synthetic maintenance fixtures

Everything under `data/` is synthetic and exists only for local development,
tests, demonstrations, and evaluation. It is not real operational data and it
must not be used to operate physical equipment.

## Canonical fixture contract

The version 1 fixture set uses these authoritative identifiers:

| Entity | IDs |
| --- | --- |
| Tenants | `company-a`, `company-b` |
| Users | `user-a-tech`, `user-a-manager`, `user-b-tech`, `user-b-manager` |
| Company A machines | `A1`, `A2` |
| Company B machines | `B1`, `B2` |

JSON files use a small envelope with `schema_version`, `generated_at`,
`provenance`, and `records`. Each record has a stable ID. Timestamps are UTC in
RFC 3339 form. Money is expressed in the currency named by the field, and
sensor units are explicit on every reading.

Core application loaders should consume the files in this order:

1. `seed/tenants.json`
2. `seed/users.json`
3. `seed/machines.json`
4. `seed/sensor_readings.json`
5. `seed/incidents.json`
6. `manuals/manifest.json` and the referenced Markdown documents

The minimum fields expected by the application are:

- tenant: `id`, `name`
- user: `id`, `tenant_id`, `name`
- machine: `id`, `tenant_id`, `name`, `model`, `line`, `status`,
  `hourly_downtime_cost`
- sensor reading: `machine_id`, `tenant_id`, `metric`, `value`, `unit`,
  `timestamp`
- incident: `id`, `tenant_id`, `machine_id`, `title`, `description`,
  `resolution`, `occurred_at`
- manual manifest record: `id`, `tenant_id`, `machine_model`, `title`, `path`

Additional fields are intentional and may be ignored by a minimal loader.
Machine IDs are unique in this fixture, but access control must still filter by
`tenant_id`; global uniqueness must never replace tenant enforcement.

## Sensor semantics

Readings are stored in long form (one metric per record) so a tool can filter by
`tenant_id`, `machine_id`, metric, and time range. `quality` is one of `good`,
`suspect`, or `missing`. A missing reading has `value: null`; it must not be
silently converted to zero or interpolated without saying so.

The most recent fixture snapshot is `2026-07-20T10:15:00Z`:

- `A1` is stopped after synthetic servo-overload alarm `E217` following a
  product changeover.
- `A2` is running with warning `VIB-HI`; one vibration sample is deliberately
  missing.
- `B1` is stopped after synthetic belt-tracking alarm `TRK-04`.
- `B2` is running normally.

These observations are fixed test facts, not live status.

## Manuals and trust boundaries

Manual Markdown headings contain stable section IDs such as
`[SP400-ALARM-E217]`. A retriever should cite the `source_reference` values in
`manuals/manifest.json` rather than inventing page numbers. The manuals are
short on purpose so chunk-level retrieval can be tested without sending every
document to a model.

`manuals/company-a-untrusted-injection-fixture.md` is an intentionally hostile
retrieval fixture. Its manifest record is marked `content_trust: untrusted` and
`document_kind: adversarial_fixture`. It contains text that attempts to change
agent policy, cross tenant boundaries, and trigger a state-changing tool. That
text is data, never an instruction. Production behavior must treat *all*
retrieved manuals, incident records, sensor metadata, and tool results as
untrusted even when the fixture label is absent.

## Validation

Schemas are under `data/schemas/` and use JSON Schema draft 2020-12. From the
repository root, any JSON Schema-compatible validator can validate each seed
file against the matching schema. The schemas allow documented extension
fields while enforcing the integration fields above.
