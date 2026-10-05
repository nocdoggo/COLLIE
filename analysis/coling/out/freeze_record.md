# Freeze record

Rendered from `analysis/coling/out/freeze_record.json`. Mode: freeze. Status: complete. Started 2026-10-05T21:25:39Z, finished 2026-10-05T21:26:48Z (UTC). Commit 26a43be48408ecc09c396213d3240e6fe5d74fe0. Hashes are the first 16 hex characters of sha256; the template pins are given whole.

The one rerun that checks the sealed hashes: started 2026-10-05T21:09:53Z; both sealed hashes and both open tables as recorded.

Written again by --continue-after-sealed. Earlier runs: started 2026-10-05T21:07:28Z, complete; started 2026-10-05T21:24:06Z, complete.

**Environment.** Python 3.12.11; the lock file `uv.lock`, hash `3308eeb43cb51580`; pandas 2.3.3, numpy 2.5.2, scikit-learn 1.9.0, scipy 1.18.1.

**Captures.** The capture manifest `analysis/coling/out/capture_manifest.csv`: hash `8104e4f23dd0c7b5`; cutoff given to the builder: 2023-12-31.

**Code (hashed at registration).**

- `corpus.py`: `a44cd27ccddad604`
- `rules.py`: `6a810bcb1ae277b9`
- `forms.py`: `b99502d348ea82be`
- `manifest.py`: `b08607c9b6623edf`
- `dataset.py`: `2fe95d355d3d5c77`
- `audit_sample.py`: `67ddfa330cf441d4`
- `audit_outcomes.py`: `0cb4d4d93eddb8ea`
- `audit_agreement.py`: `0a040e036d2b7697`
- `sealed_counts.py`: `22d592e0b65b339b`
- `freeze.py`: `0850418be7315cb0`
- `predictors.py`: `452254cac0cb7817`
- `gbm.py`: `1e5eb3791e90b587`
- `power.py`: `6948ee5f2f27e111`
- `track_record.py`: `53873bade0dd0e4b`

**Tables.**

- Sealed, as printed by the freeze run: `outcomes_test.csv.gz` `67df1acccd9a7174`; `outcomes_train_uncensored.csv.gz` `6f4d96d7e18d878a`.
- Open: `events.csv.gz`, gzip file `d8d970a91691e702`, decompressed content `41f723e3debea466`.
- Open: `outcomes_train.csv.gz`, gzip file `8772acd6b63afa36`, decompressed content `d114076e052819d6`.
- The E3 eligible list `analysis/coling/out/eligible_e3.csv` (2593 statements): file `8c12fc3e940f250e`, ids `a65983839e361c6e`.
- Secondary list `tbd` (376 statements): ids `49466e77d6649d73`.
- Secondary list `silent` (550 statements): ids `e2e69a03c89c1d2c`.
- Secondary list `stale` (16 statements): ids `be48aa1e4b00e9f9`.
- Sample list `pilot` (`analysis/coling/out/audit/samples/sample_pilot.csv`, 20 rows): `edd0c9c477b83f79`.
- Sample list `check` (`analysis/coling/out/audit/samples/sample_check.csv`, 20 rows): `eb80b0fc1ceb2485`.
- Sample list `reserve` (`analysis/coling/out/audit/samples/sample_reserve.csv`, 20 rows): `6be05e4f1a000cbd`.
- Sample list `literal` (`analysis/coling/out/audit/samples/sample_literal.csv`, 120 rows): `05fcaf84b77406d7`.
- Sample list `outcome_audit_train` (`analysis/coling/out/audit_outcomes/outcome_train_sample.csv`, 56 rows): `53a1c2449c26a233`.
- Sample list `later_dev_prompt` (`analysis/coling/out/audit/samples_later/sample_dev_prompt.csv`, 60 rows): `b404466c9a22a1b6`.
- Sample list `later_incontext_pool` (`analysis/coling/out/audit/samples_later/sample_incontext_pool.csv`, 50 rows): `ba42ebab7b3d1bb6`.
- Sample list `later_pair_seeds` (`analysis/coling/out/audit/samples_later/sample_pair_seeds.csv`, 100 rows): `17caf511bf2bf3e1`.

**Annotation.**

- `analysis/coling/plan/AUDIT_GUIDE.md` (version line: v1): `c7a73851be7246fa`.
- The availability-string list `analysis/coling/out/availability_strings.csv`: `da0bde1baac48473`.

**Counts.** The Gate 1 record (section 12):

```
Gate 1: shortage events dated 2023-01-01..2025-12-31, Current at statement, with a date-like phrase
  statement events 4328; distinct statements 3134 (need >= 600)
  observable outcome (bracket <= 31 d), definition B: presentation-level events 2011, distinct statements 1422 (need >= 250)
  observable outcome (bracket <= 31 d), definition A: presentation-level events 590, distinct statements 405 (secondary, no threshold)
  shortage episodes 123 (need >= 100)
  dated after 2023-12-31, observable outcome, definition B: presentation-level events 1205, distinct statements 834 (need >= 150)
  dated after 2023-12-31, observable outcome, definition A: presentation-level events 334, distinct statements 214 (secondary, no threshold)
  dated after 2023-12-31: events 2679, distinct statements 1948; with follow-up 2677, distinct with follow-up 1947 (no threshold)
  builder's gate set: met
Gate 1 on the E3 eligible list (counts-only code, displayed presentation):
  statements 2593 (need >= 600): met
  observable 1275 (need >= 250): met
  episodes 115 (need >= 100): met
  post_cutoff 714 (need >= 150): met
  scoreable statements 1903 (no threshold)
  eligible list: met
```

The counts of `analysis/coling/out/sealed_counts.json`, as registered:

```
e3_eligible_test.eligible_statements: 2593
e3_eligible_test.eligible_episodes: 115
e3_eligible_test.scoreable_statements: 1903
e3_eligible_test.scoreable_episodes: 106
e3_eligible_test.undetermined_statements: 690
post_cutoff_slices.scoreable_statements.llama-3.3-70b: 1121
post_cutoff_slices.scoreable_statements.deepseek-v3: 411
post_cutoff_slices.scoreable_statements.qwen-2.5-7b: 549
post_cutoff_slices.scoreable_statements.gemma-3-27b: 607
post_cutoff_slices.scoreable_statements.gpt-oss-20b: 679
post_cutoff_slices.scoreable_statements.gpt-4o-mini: 1253
gate1_on_the_eligible_list.observable_statements: 1275
gate1_on_the_eligible_list.observable_statements_after_cutoff: 714
```

**Models.** `analysis/coling/plan/MODELS.md`: `747035397da93c93`.

**Prompts.**

- `literal-free-v1`: `ab87cd7525a49965763f78f55d6f8c47f4ca1476f49216a525635f97d6ef2555`
- `literal-v1`: `855244013a7614501ebdd6fbb45c8998f102a877e1299a6d86f81e1359934b27`
- `predictive-track-v1`: `d0384c1f860d734bd26fa197de0a99e1bcdf520392941b399ef9d0f7b3213483`
- `predictive-v1`: `c0732a5b2d109c60a94e56cd0820a4aa5851786bd01fd31acd3b12c9d47534ed`
- `probe-v1`: `02e8d4338c3532a22615a43c47c54423250bf13474ef3f556925f5c878e8d08e`
