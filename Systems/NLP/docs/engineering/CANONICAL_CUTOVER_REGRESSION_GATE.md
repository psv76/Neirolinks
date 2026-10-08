# Canonical placement regression gate — Issue #147

The canonical repository preparation at commit `2c0062e` exposed nine failing
regression cases and three Ruff format deviations. This gate does not change
the live database, schema, DWG or installed source launcher.

## Synchronization corrections

- Safe chained CableLine renames resolve accepted baselines from the original
  baseline snapshot, even when a new owner path already belongs to another
  moving line. Aliases must not consume previously rewritten alias values.
  Apply still verifies the original accepted baseline and Project revision.
- An unambiguous legacy base-only EL_BOX CablePoint is adopted before stale
  topology pruning. Its point identity is preserved; ambiguous collapsed points
  remain explicit errors and are not split by guessing.

## Regression contract alignment

- Workflow DTO fixtures include `dwg_value`, which is required by SyncChange.
- A selectively imported downstream line cannot use an unaccepted distribution
  box. The error identifies that missing dependency and the operation rolls back.
- Accepted Excel export controls remain available while the cable journal works
  inside the application. The prior assertion forbidding all export controls is
  obsolete after accepted commits `9eb8093` and `31d676e`.
- Specification navigation follows the accepted source tree (`e237d33`): expand
  an aggregate row and double-click the desired source. The test verifies return
  navigation, selection and unchanged Project revision through this interaction.

## Validation boundary

Run format/check and all non-live, non-manual tests with dedicated runtime roots
and a forward-slash pytest basetemp outside the source tree. Record actual
results and the final commit in Issue #147. Passing this gate does not establish
GUI cutover acceptance or authorize removal of `D:\NL_Project_2_Main`.
