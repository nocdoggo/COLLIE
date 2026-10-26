# Presentation notes

Predictive Prefetching for Retrieval-Augmented Generation
Wuyang Zhang and Shichao Pei, University of Massachusetts Boston, ICML 2026

Read each paragraph at a steady, clear pace. At a medium speed the full script runs to about four minutes and twenty five seconds, which leaves a safe margin under the four forty five cap. Pause briefly each time you advance a slide. The short time estimate under each heading is a guide, not a target to rush toward.

---

## Slide 1. Title page
_about 12 seconds_

Hello everyone. This is our work on predictive prefetching for retrieval augmented generation, by Wuyang Zhang and Shichao Pei from the University of Massachusetts Boston.

---

## Slide 2. The latency bottleneck in RAG
_about 35 seconds_

Retrieval augmented generation grounds a language model in external knowledge. It works well, but it is slow. Each external retrieval costs one hundred to five hundred milliseconds, and hard queries trigger many. Today's systems are synchronous, so when the model becomes uncertain and asks for retrieval, it stops generating and waits, here for two hundred and eighty seven milliseconds. Recent parallel methods hide that time, but they query with stale heuristics, so they fetch the wrong content.

---

## Slide 3. Key insight, information needs are foreshadowed
_about 35 seconds_

The need for retrieval does not appear out of nowhere. Several tokens before the model gets stuck, its internal state has already shifted, in entropy, attention, and value vectors. We can read these signals about eight to sixteen tokens early, enough lead time to retrieve in the background. The same signals also tell us what to look for, so the query is ready before the gap appears. As the figure shows, we predict early, prefetch in the background, and generation never stops.

---

## Slide 4. Approach, decouple retrieval from generation
_about 38 seconds_

The framework decouples retrieval from generation using three learned components. The retrieval predictor decides when to trigger, from internal signals. The context monitor decides whether we have enough context, and how long to wait so the query is not half formed. The query generator decides what to fetch, using a small T five model. Retrieval runs in the background, results are used with no added latency, and a synchronous fallback keeps the answer correct when a prediction misses.

---

## Slide 5. Learning, pretrain once then adapt online
_about 28 seconds_

All three components are trained together. The labels come automatically from generation traces, so there is no manual annotation. After deployment the system keeps adapting with a policy gradient, and because each decision gets its own immediate feedback, the reward updates only the component that made it. The whole stack adds sixty two million parameters and under three milliseconds per token.

---

## Slide 6. Results, latency down and quality held
_about 34 seconds_

Synchronous retrieval is accurate but slow, two hundred and eighty seven milliseconds to the first token and nine point two seconds end to end. We cut time to first token by about sixty two percent, end to end latency by about forty three percent, and use about a third fewer retrievals. Quality stays within one point of synchronous retrieval, and against the strongest prior parallel method we are better on both quality and speed at once.

---

## Slide 7. Why it works, accurate and well timed prediction
_about 32 seconds_

Two things make this work. The learned predictor reaches an AUROC of zero point eight one, against zero point six six for thresholding the current entropy, so it is far better at spotting needs early. High confidence predictions give about nine tokens of lead, enough to finish a retrieval. And waiting just three or four tokens lets a phrase complete and raises query relevance by up to twenty three percent.

---

## Slide 8. It holds up across settings
_about 27 seconds_

The method also generalizes. As we sweep retrieval latency, the benefit peaks around two hundred milliseconds and falls off gently, and the synchronous fallback means the worst case is never worse than the baseline. The same settings drive six different models, and we see gains on code completion and summarization too. Even the tail is controlled, since a missed prediction still beats synchronous retrieval.

---

## Slide 9. Takeaway
_about 18 seconds_

To wrap up. The need for retrieval is predictable from the model's own dynamics, several tokens ahead. By learning when, whether, and what to retrieve, we hide latency without giving up relevance. Thank you, and I am happy to take questions.
