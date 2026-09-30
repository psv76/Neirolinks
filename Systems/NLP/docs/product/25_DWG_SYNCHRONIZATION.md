# NL Project 2.0 — контракт синхронизации с DWG

## Active Repair08 synchronization contract (normative)

Sync сохраняет P0_003 three-way owner-aware engine: immutable observation batch -> exact validation -> normalized owner facts/topology plans -> baseline/Project/DWG classification -> deterministic preview -> explicit atomic apply или exact write plan/read-back. DWG автоматически не сохраняется.

Owners: insertion planning facts; CableLine (`BOARD`, `CABLE_TYPE`); CableSegment (`CABLE_SOURCE`, ordinary route); bus (`BUS_CABLE_TYPE`, Project-owned root/type); BusSegment (`BUS_SOURCE` where applicable, bus route); physical ports; control keys. Derived/retired values не являются editable planning owners.

Downstream `CABLE_SOURCE=<BUS_POINT_ID>/<PORT>` и reciprocal output-port value — две editable projections одного canonical edge. Previous accepted Project baseline resolves one-side changes and consistent two-side changes. Incompatible two-side change emits `DUAL_PROJECTION_REQUIRES_ATTENTION`, blocks only dependent selected operation and never chooses silently. Materialization updates one CableSegment by target endpoint and synchronizes the opposite projection.

Ordinary topology uses `CABLE_SOURCE=<empty>|BOX.NNN|XYY.ZZ|9YY.ZZZ/PORT`; root derives from canonical source endpoint. DALI uses `.000` root and explicit branching; RS-485 uses numeric `.ZZZ` without `BUS_SOURCE`. Physical BusSegment route and ordinary CableSegment route remain independent. Track links create no external cable/conduit.

Project-to-DWG may write only a Project-originated/resolved value that is both in the closed allow-list and present in the exact ATTDEF set of the observed Repair08 canonical block. It never emits retired tags/names or Project-derived type/post/link/root/bus facts. Binding, revision, Handle, name/layer and exact read-back are mandatory.

Exact names/ATTDEF and topology semantics are owned by `docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md` and `docs/autocad/CURRENT_TOPOLOGY_ARCHITECTURE.md`. Machine contract version is `3.0.0` with 71 definitions.
