# Confirmatory results (PLAN.md section 6)

Registered p-values: larger_of_studentised_and_sign_flip_t. Intervals of the six contrasts and of Delta_GBM: values_not_rejected_by_the_registered_test. H3 comparator rule: base_rate. Holm over 6 tests at 0.05; 10000 draws by shortage episode, seed 20261001. Delta is the comparator's mean primary Brier minus the tested predictor's.

| Test | Model | Comparator | Tested | Items | Statements | Episodes | Delta | 95% interval | p | Holm p | Reading |
|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | llama-3.3-70b | llama-3.3-70b:a | llama-3.3-70b:b | the post-cutoff slice | 1121 | 85 | 0.0561 | [-0.0020, 0.1122] | 0.0284 | 0.1572 | not rejected |
| H2 | llama-3.3-70b | rules_plus_slip | llama-3.3-70b:c | the post-cutoff slice | 1121 | 85 | 0.0010 | [-0.0138, 0.0094] | 0.9219 | 0.9219 | not rejected |
| H3 | llama-3.3-70b | base_rate | llama-3.3-70b:b | the post-cutoff slice | 1121 | 85 | -0.0177 | [-0.0370, -0.0019] | 0.0262 | 0.1572 | not rejected |
| H1 | deepseek-v3 | deepseek-v3:a | deepseek-v3:b | the post-cutoff slice | 411 | 58 | 0.0613 | [-0.0261, 0.1406] | 0.0738 | 0.2952 | not rejected |
| H2 | deepseek-v3 | rules_plus_slip | deepseek-v3:c | the post-cutoff slice | 411 | 58 | 0.0048 | [-0.0008, 0.0124] | 0.0990 | 0.2970 | not rejected |
| H3 | deepseek-v3 | base_rate | deepseek-v3:b | the post-cutoff slice | 411 | 58 | -0.0092 | [-0.0363, 0.0110] | 0.3970 | 0.7939 | not rejected |

H2 equivalence, llama-3.3-70b: declared by the rule, which needs both one-sided p-values below 0.05 at the margin of 0.02: 0.0013 at -0.02 and 0.0001 at 0.02 (90% interval, reported beside the rule and not read for it: [-0.0118, 0.0084]). The two losses differ on 112 statements in 38 episodes: 26 with a positive sum, 12 with a negative one, 0 whose differences cancel.
Beside H3, llama-3.3-70b: gbm_structured minus llama-3.3-70b:b: delta -0.0140, 95% interval [-0.0461, 0.0184]; beats both comparators: no; answers of the tested condition not parsed: 0.
H2 equivalence, deepseek-v3: declared by the rule, which needs both one-sided p-values below 0.05 at the margin of 0.02: 0.0001 at -0.02 and 0.0002 at 0.02 (90% interval, reported beside the rule and not read for it: [0.0000, 0.0108]). The two losses differ on 31 statements in 21 episodes: 13 with a positive sum, 8 with a negative one, 0 whose differences cancel.
Beside H3, deepseek-v3: gbm_structured minus deepseek-v3:b: delta -0.0103, 95% interval [-0.0494, 0.0239]; beats both comparators: no; answers of the tested condition not parsed: 0.
Probe, llama-3.3-70b: delta 19.5602 days of pinball loss at 0.5 (base rate minus probe), p 0.0019; tests on: the post-cutoff slice.
Probe, deepseek-v3: delta 18.1329 days of pinball loss at 0.5 (base rate minus probe), p 0.0053; tests on: the post-cutoff slice.
Overconfidence of condition (a), llama-3.3-70b: reading 2 of 5: the readings are overconfident relative to outcomes. P(E_end) on the post-cutoff slice (1524 statements in 91 episodes, 289 with E_end undetermined): mean 0.5327. Against outcomes: least value of calibration in the large 0.1226 [0.0661, 0.1799] (every undetermined E_end counted as yes: frequency 0.4101), greatest 0.3123 [0.2623, 0.3608] (counted as no: frequency 0.2205); part met. Against the base rate (mean P(E_end) 0.2345): difference 0.2982 [0.2735, 0.3255]; part met.
Overconfidence of condition (a), deepseek-v3: reading 2 of 5: the readings are overconfident relative to outcomes. P(E_end) on the post-cutoff slice (591 statements in 63 episodes, 139 with E_end undetermined): mean 0.6200. Against outcomes: least value of calibration in the large 0.1716 [0.0985, 0.2405] (every undetermined E_end counted as yes: frequency 0.4484), greatest 0.4068 [0.3399, 0.4669] (counted as no: frequency 0.2132); part met. Against the base rate (mean P(E_end) 0.2222): difference 0.3977 [0.3705, 0.4223]; part met.
