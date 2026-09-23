# Pilot report (2026-09-23)

Requested episodes: 120

Pilot manifest: `H:\AI_Paper\COLLIE\reports\pilot_manifest.json`

Decision: **kill-or-reframe**

## Go Criteria

| id | estimate | ci_low | ci_high | operator | threshold | verdict | source |
|---|---:|---:|---:|---:|---:|---|---|
| `profit_lift` | 37.75 | 15.2396 | 60.2604 | `>=` | 0 | pass | computed |
| `lost_sales_reduction` | 9.4375 | 3.80989 | 15.0651 | `>=` | 0 | pass | computed |
| `false_activation_control` | 0.958333 | 0.876668 | 1.04 | `>=` | 0.95 | fail | computed |
| `wrong_family_exposure` | 0.0127083 | 0.00631977 | 0.0190969 | `<=` | 0.1 | pass | computed |
| `fill_rate_floor` | 0.887593 | 0.875554 | 0.899631 | `>=` | 0.95 | fail | computed |
| `cost_frontier` | 0 | 0 | 0 | `>=` | 1 | fail | computed |
| `recovery_time` | 26.5833 | 21.6677 | 31.499 | `<=` | 4 | fail | computed |

## Kill Or Reframe Triggers

| id | estimate | ci_low | ci_high | operator | threshold | verdict | source |
|---|---:|---:|---:|---:|---:|---|---|
| `insufficient_headroom` | 2 | 2 | 2 | `<=` | 3 | triggered | computed |
| `detector_indistinguishable` | -565.533 | -708.611 | -422.455 | `<=` | 0 | triggered | computed |
| `false_activation_rate` | 0.0416667 | -0.0399985 | 0.123332 | `>=` | 0.1 | clear | computed |
| `wrong_family_activation_rate` | 0.197917 | 0.117797 | 0.278036 | `>=` | 0.25 | clear | computed |
| `parser_failure_rate` | 0 | 0 | 0 | `>=` | 0.1 | clear | computed |
| `budget_overrun_rate` | 0 | 0 | 0 | `>=` | 0.1 | clear | computed |
| `negative_profit_lift` | 37.75 | 15.2396 | 60.2604 | `<=` | 0 | clear | computed |
| `method_freeze_or_quarantine_violation` | 0 | missing | missing | `==` | none | clear | computed |
