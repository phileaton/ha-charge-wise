# Architectural Decisions

## Decision Log

### Derive charger control from Home Assistant entities

**Date:** 2026-10-29

**Context:** Charger controls and energy measurements already exist as Home Assistant entities, but the selected
entities and their vendor integrations vary by installation. The controller needs prompt updates without polling
several unrelated sources or adding a vendor-specific API dependency.

**Decision:** Configure the source and control entity IDs in each Charge Wise entry. Calculate decisions in a pure
controller and reevaluate from entity state changes and controller timers. Model each charger entry as its own Home
Assistant device, with entity unique IDs scoped to the entry.

**Rationale:**

- Entity listeners use the state each source integration already publishes and avoid duplicate polling.
- A pure decision engine makes the current-limit, Solar, battery, and cooldown rules testable without Home Assistant
  service calls.
- Separate entries let users combine different chargers and energy sources without a vendor-specific adapter layer.
- A vendor API client would duplicate the configured Home Assistant integrations and make charger support less
  hardware-agnostic.

**Consequences:**

- Users must select and maintain the source entities; Charge Wise does not discover devices or validate vendor
  connectivity.
- Source integrations determine update frequency and data freshness. Charge Wise pauses Solar when required readings
  are unavailable but does not inspect source-specific timestamps or impose a generic stale-reading timeout.
- Each entry represents one charger and cannot share its switch or active current target with another Charge Wise
  entry.
- Entry-scoped entity IDs are stable for an entry, but removing and recreating that entry creates a new identity.
