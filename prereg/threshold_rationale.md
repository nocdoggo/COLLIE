# Pilot Threshold Rationale

**Decision date:** 2026-09-22  
**Applies to:** `prereg/prereg_v1.yaml` version 1  
**Decision state:** frozen before the formal pilot and all held-out test trajectories

## Decision rule

The formal pilot uses 120 independent dev/cal units. Every go criterion must pass using the
conservative side of its 95% interval: a lower-bound criterion uses the interval's lower bound and
an upper-bound criterion uses its upper bound. A point estimate alone cannot issue a go decision.
Any kill trigger produces a `kill-or-reframe` decision even when every go criterion passes.

The values below were selected from the registered statistical guarantees, hard implementation
limits, the original design's pilot rules, and exploratory dev-only diagnostics. They were not
selected from formal-pilot or held-out test outcomes.

## Go criteria

| Criterion | Threshold | Reason |
|---|---:|---|
| Profit lift | `>= 0` | ARM10 must improve cumulative undiscounted profit over ARM1. Requiring the lower confidence bound to clear zero supplies the materiality guard without inventing a currency-scale margin that changes across episodes. |
| Lost-sales reduction | `>= 0` | ARM10 must reduce total lost-sales units relative to ARM1. The paired lower confidence bound must clear zero. |
| False-activation control | `>= 0.95` | The verifier registers `alpha_episode = 0.05`; control is defined as one minus the episode-level false-activation rate. |
| Wrong-family exposure | `<= 0.10` | Wrong-family activation has no theorem-backed bound. Ten percent limits the mean period-level exposure while leaving room to observe and diagnose occasional empirical errors. |
| Fill-rate floor | `>= 0.95` | The operational definition of recovery already uses a 0.95 fill-rate target. The aggregate service gate uses the same target rather than introducing a second service standard. |
| Cost-frontier membership | `>= 1` | This metric is binary. ARM10 must appear on the realised profit-cost Pareto frontier. |
| Recovery time | `<= 4` | Four periods matches the largest registered finite promised lead time. Recovery means the first of three consecutive periods at or above 0.95 fill rate after the final shock-active period. |

An episode that never recovers is assigned `horizon + 1`. The registered horizon is 50, so the
score is 51. This prevents failed recoveries from disappearing from the mean.

## Kill thresholds

| Trigger | Threshold | Reason |
|---|---:|---|
| Insufficient headroom | `<= 3` passing families | The original design requires oracle ShockSpec to improve raw profit by at least 5%, or CVaR10 by at least 10%, on at least four of six shock families. Three or fewer passing families triggers a reframe. |
| Detector indistinguishable | `<= 0` | ARM10 must beat the detector-to-compiler control on cumulative undiscounted profit. A non-positive paired contrast means language has not added value over statistical detection. |
| False-activation rate | `>= 0.10` | Ten percent is twice the registered 0.05 nominal level and operationalizes the design's phrase "substantially exceeds nominal levels." |
| Wrong-family activation rate | `>= 0.25` | One wrong-family activation in four affected episodes is too frequent for a persistent control intervention and requires reframing or repair. |
| Parser-failure rate | `>= 0.10` | Each proposal already receives one constrained repair attempt. Ten percent terminal failure after that repair path is an unacceptable interface failure rate. |
| Budget-overrun rate | `>= 0.10` | More than ten percent of episodes exceeding the hard registered call budget indicates that the sparse-compute claim is not operationally reliable. |
| Negative profit lift | `<= 0` | A non-positive ARM10-minus-ARM1 profit contrast is a direct no-benefit boundary and triggers a reframe. |

## Call budget

The registered call budget is four call records per ARM10 episode. The trigger permits at most two
proposals, and each proposal permits one initial call and one format-repair call. Repairs are real
calls and remain in the denominator. The pilot runner rejects any CLI budget that differs from four.

## Dev evidence consulted

The module-06 scripted 18-episode dev diagnostic was inspected only as a scale and consistency
check. It is explicitly placeholder-grade and is not formal-pilot evidence. In that diagnostic:

- ARM1 mean raw profit was `17629.11`; ARM10 was `17675.78`, a difference of `+46.67`.
- ARM1 mean lost sales were `679.61`; ARM10 was `667.94`, a reduction of `11.67`.
- ARM10 normalized reward was `0.0138` below ARM1 despite its small raw-profit increase.
- Oracle raw-profit lift cleared 5% only for demand-level (`6.60%`) and lead-time-shift
  (`18.47%`). The newly completed compound oracle measured `0.008%`, so the diagnostic still
  clears the registered headroom rule on only two of six families.

The headroom threshold was retained even though this diagnostic would currently trigger it. Moving
the threshold to accommodate that result would defeat the purpose of preregistration. The diagnostic
instead identifies a real compiler/task-calibration risk to resolve or report through the pilot.

## Known interpretation constraints

- Profit and lost-sales go metrics are absolute paired differences. Their zero thresholds are
  interpreted through conservative confidence bounds, not point estimates.
- `shock_periods` supplied to evaluation must identify the final shock-active period, not onset.
- Headroom requires oracle and ARM1 records for all six generator families. The primary
  stratum weights use the stored `ShockFamily` labels: both demand-level generator directions
  share the `demand_level` label, and generator family 6 is stored as `compound`.
- Detector distinguishability requires the detector-to-compiler control on the same independent
  units as ARM10.
- Wrong-family thresholds are empirical operating tolerances, not theorem-backed guarantees.
