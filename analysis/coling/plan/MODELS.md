# Models: cutoffs, routes, provider pins and prices, checked at source

This note fills the **TBD-at-registration** items of `PLAN.md` sections 3, 4 and 17 (DECISIONS 14
and 17) for the eight readers. Every fact below was read on **2026-10-01 (UTC)** from the page
named next to it: a model card, the provider's own documentation, or OpenRouter's public
per-model endpoint listing. No model was called and no key was used. Every primary source was
then read again on the same day, twice, each time without relying on the earlier reading; the
corrections are folded in. Where a value that moves from hour to hour (an endpoint's status or
uptime) differed between readings, section 3 says so.

The requests carried nothing personal. They went through a general page-fetching tool that sets
its own User-Agent, so they did not carry the project string of process rule 8 (`DECISIONS.md`).
Three documents were read as the full text of their PDF: the DeepSeek-V3 and Qwen2.5 technical
reports and the gpt-oss model card. The other pages were read as text extracted from the page,
and the quotations below are as that text gave them.

- **documented** means the page states it in words that are quoted here.
- **none documented** means the pages listed were read and state no cutoff; the release month is
  then the bound (PLAN section 3; DECISIONS 17).
- **UNVERIFIED** means the fact could not be confirmed at a primary source and must not be
  written into the plan as a fact.

The note holds no study count. Slice sizes follow from the cutoff months below and are printed
by the counts-only script, not here.

**To repeat the check** (for example if registration slips): open the URLs in sections 2 to 6
again, compare, and change the retrieval date. Endpoint lists, uptimes and prices in section 3
move from day to day; cutoffs, release dates and ids should not.

**Owner review.** DECISIONS 14 asks the owner to review the two primaries. The lines to re-open
are marked **(primary)**; the open choice for `deepseek-v3` is in section 5.

## 1. Summary

| Model | Role | Released | Training cutoff | Post-cutoff slice starts after | Status of the cutoff |
|---|---|---|---|---|---|
| llama-3.3-70b **(primary)** | primary | 2024-12-06 | December 2023 | 2023-12-31 | documented (model card) |
| deepseek-v3 **(primary)** | primary | 2024-12-26 | none stated | 2024-12-31 | none documented; bounded by the release month |
| qwen-2.5-7b | secondary | 2024-09-19 | none stated | 2024-09-30 | none documented; bounded by the release month |
| gemma-3-27b | secondary | 2025-03-12 | August 2024 | 2024-08-31 | documented (model card) |
| gpt-oss-20b | secondary | 2025-08-05 | June 2024 | 2024-06-30 | documented (model card; provider model page) |
| gpt-4o-mini | secondary | 2024-07-18 | October 2023 ("Oct 01, 2023") | 2023-10-31 | documented (provider model page) |
| gemini-3.8-flash | secondary | 2026-09-02 | March 2026, with a caveat (below) | 2026-03-31 | documented (model card) |
| grok-4.20 | secondary | 2026-03 | none stated for this model | 2026-03-31 | none documented; bounded by the release month |

| Model | Route and id | Endpoint to pin (recommended) | Precision at the pin | $/1M in | $/1M out | PLAN section 4 price | Change |
|---|---|---|---|---|---|---|---|
| llama-3.3-70b | OpenRouter `meta-llama/llama-3.3-70b-instruct` | `deepinfra/turbo` | fp8 | 0.10 | 0.32 | 0.10 / 0.32 | none |
| deepseek-v3 | OpenRouter `deepseek/deepseek-chat` | `deepinfra/fp4` (alternative: `streamlake`) | fp4 (alternative: not stated) | 0.32 | 0.89 | 0.257 / 1.029 | price changes with the pin; the plan's price is the `streamlake` endpoint's |
| qwen-2.5-7b | OpenRouter `qwen/qwen-2.5-7b-instruct` | `phala` (the only endpoint) | not stated | 0.10 | 0.20 | 0.10 / 0.20 | none |
| gemma-3-27b | OpenRouter `google/gemma-3-27b-it` | `deepinfra/fp8` | fp8 | 0.08 | 0.16 | 0.08 / 0.45 | output price; the plan's price is the `parasail/fp8` endpoint's |
| gpt-oss-20b | OpenRouter `openai/gpt-oss-20b` | `deepinfra/bf16` | bf16 | 0.03 | 0.14 | 0.018 / 0.09 | both prices; the plan's price is the `darkbloom/fp8` endpoint's |
| gpt-4o-mini | OpenRouter `openai/gpt-4o-mini` (alias of the only snapshot, `gpt-4o-mini-2024-07-18`; a dated route `openai/gpt-4o-mini-2024-07-18` also exists) | `openai` | not applicable | 0.15 | 0.60 | 0.15 / 0.60 | none (section 8 on the dated route) |
| gemini-3.8-flash | Google `gemini-3.8-flash` (the only id; no dated snapshot is listed) | direct | not applicable | 0.75 | 3.75 | 0.75 / 3.75 | none until 2026-12-31 |
| grok-4.20 | xAI `grok-4.20-0309-non-reasoning` (dated id) | direct | not applicable | 1.25 | 2.50 | 1.25 / 2.50 | none (prompts under 200k tokens) |

## 2. Cutoffs and release dates, with sources

All retrieved 2026-10-01.

**llama-3.3-70b (primary).** *Documented: December 2023.*
- Model card, `https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct`: "Data Freshness: The
  pretraining data has a cutoff of December 2023." The card's table gives "Knowledge cutoff:
  December 2023" and "Model Release Date: 70B Instruct: December 6, 2024". Released weights are
  BF16.
- This agrees with the constant `2023-12-31` in `corpus.py` used by the fourth Gate 1 threshold.

**deepseek-v3 (primary).** *None documented. Bound: December 2024.*
- Model card, `https://huggingface.co/deepseek-ai/DeepSeek-V3`: states no training-data or
  knowledge cutoff. It links the technical report arXiv:2412.19437 and says of the weights:
  "Since FP8 training is natively adopted in our framework, we only provide FP8 weights."
- Technical report, `https://arxiv.org/abs/2412.19437` (v1 2024-12-27, v2 2025-02-18): states
  no cutoff. The full text of v2 (`https://arxiv.org/pdf/2412.19437v2`, 53 pages, appendices
  included) was searched for "cutoff", "cut-off" and for dates attached to the training corpus.
  Section 4.1 gives the size of the corpus ("14.8T high-quality and diverse tokens") and no
  date. The only dates in the text belong to evaluation sets (for example LiveCodeBench,
  "collected from August 2024 to November 2024"), which say nothing about the training data.
- DeepSeek API change log, `https://api-docs.deepseek.com/updates`: "2024-12-26 ... The
  `deepseek-chat` model has been upgraded to DeepSeek-V3." No cutoff is stated anywhere in the
  log.
- Repository history, `https://huggingface.co/deepseek-ai/DeepSeek-V3/commits/main`: created
  2024-12-25 (UTC); the weight uploads and the commit "Release DeepSeek-V3" are all dated
  2024-12-26. Eight commits follow (to 2025-03-27, head
  `e815299b0bcbac849fa540c768ef21845365c9eb`).
  - By their messages, six of them change the README files, the citation, the library metadata
    and a helper script. The other two were opened: the head commit ("Small fix") changes
    `config.json`, `configuration_deepseek.py` and `modeling_deepseek.py`, and `108e1e0`
    changes `README_WEIGHTS.md`.
  - None of the eight is described as, or was seen to be, a change of a weight file; six were
    judged by their messages only.
  - The repository therefore holds one set of weights, those of December 2024 (163
    `model-*.safetensors` files in `https://huggingface.co/api/models/deepseek-ai/DeepSeek-V3`).
    V3-0324 has a repository of its own (`deepseek-ai/DeepSeek-V3-0324`, created 2025-03-24).
- Release date used: 2024-12-26 (the change-log entry and the weight release; OpenRouter lists
  the model as created on the same day).

**qwen-2.5-7b.** *None documented. Bound: September 2024, not October.*
- Model card, `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct`: states no cutoff; the citation
  block gives "month = {September}, year = {2024}". Released weights are BF16. The repository
  was created on 2024-09-16 (`https://huggingface.co/api/models/Qwen/Qwen2.5-7B-Instruct`).
- Release post, `https://qwenlm.github.io/blog/qwen2.5/`: dated "September 19, 2024"; states no
  cutoff.
- Technical report, `https://arxiv.org/abs/2412.15115`: states no cutoff. The full text of v2
  (`https://arxiv.org/pdf/2412.15115v2`, 26 pages) was searched for "cutoff", "cut-off" and for
  dates attached to the training data; there is none.
- The "2024-10" of the draft plan and of the ladder file is the month in which OpenRouter
  listed the route (created 2024-10-16), not the month of the model's release.

**gemma-3-27b.** *Documented: August 2024.*
- Model card, `https://ai.google.dev/gemma/docs/core/model_card_3` (page last updated
  2025-08-14): "The knowledge cutoff date for the training data was August 2024."
- Release post, `https://blog.google/technology/developers/gemma-3/`: dated "Mar 12, 2025".
- The Hugging Face card (`https://huggingface.co/google/gemma-3-27b-it`) shows BF16 weights; the
  cutoff sentence was not visible there, so the Google page above is the source.

**gpt-oss-20b.** *Documented: June 2024.*
- Model card by the maker, "gpt-oss-120b & gpt-oss-20b Model Card", as deposited at
  `https://arxiv.org/abs/2508.10925` (v1; full text read, 35 pages), section 2.4: "Our model has
  a knowledge cutoff of June 2024." Its title page is dated "August 5, 2025".
- Provider model page, `https://developers.openai.com/api/docs/models/gpt-oss-20b` (the old
  `platform.openai.com/docs/models/gpt-oss-20b` redirects there): "Jun 01, 2024 knowledge
  cutoff"; one snapshot, `gpt-oss-20b`. The page prints a month as its first day; the model card
  gives the month, and the slice rule takes the whole month, which is the later reading.
- Hugging Face card, `https://huggingface.co/openai/gpt-oss-20b`: states no cutoff; describes
  "MXFP4 quantization of the MoE weights" in the released files (tensor types BF16 and U8).
- Release date 2025-08-05: the date on the model card, and the day OpenRouter lists the model
  as created. The announcement page (`https://openai.com/index/introducing-gpt-oss/`) could not
  be opened (HTTP 403).

**gpt-4o-mini.** *Documented: October 2023.*
- Provider model page, `https://developers.openai.com/api/docs/models/gpt-4o-mini`: "Oct 01,
  2023 knowledge cutoff" (a month printed as its first day, as for gpt-oss-20b). One snapshot is
  listed, `gpt-4o-mini-2024-07-18`, and the alias `gpt-4o-mini` points to it.
- `https://developers.openai.com/api/docs/deprecations`: neither id is listed as deprecated
  (other `gpt-4o-mini-*` variants, such as the audio and search previews, are).

**gemini-3.8-flash.** *Documented: March 2026, uneven across domains.*
- Model card, `https://deepmind.google/models/model-cards/gemini-3-8-flash/` ("Published
  2 September 2026"): "The knowledge cutoff date for Gemini 3.8 Flash is March 2026 – users can
  expect updated information for some domains while in others they may experience the model's
  knowledge is limited to January 2025 (in line with the Gemini 3 Model Family)."
- API model page, `https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash`: model code
  `gemini-3.8-flash`; "Versions: Stable: `gemini-3.8-flash`"; "Latest update: September 2026";
  thinking "Supported (low, medium, high)" and "'minimal' is not supported and returns an
  error". The page has no knowledge-cutoff row.
- `https://ai.google.dev/gemini-api/docs/deprecations`: release date "September 2, 2026"; "No
  shutdown date announced".
- The cutoff month to register is March 2026 (the later of the two the card names), which is the
  conservative choice for a memory control.

**grok-4.20.** *None documented. Bound: March 2026.*
- Model page, `https://docs.x.ai/docs/models/grok-4.20-0309-non-reasoning`: no cutoff is stated.
  The id `grok-4.20-0309-non-reasoning` is dated; eight aliases are listed, among them
  `grok-4.20-non-reasoning` and `grok-4.20-non-reasoning-latest`.
- Models overview, `https://docs.x.ai/docs/models`: the only cutoff sentence is "The knowledge
  cut-off date of Grok 4.7 is May 2026." Nothing is said about Grok 4.20.
- Release notes, `https://docs.x.ai/docs/release-notes`: "Grok 4.20 and Grok 4.20 Multi-agent
  are live" under the heading "March". From the top the headings run September, August, July,
  June, May, April, March, January, then December 2025 and back to November 2024. Those of this
  year carry no year; that this "March" is March 2026 follows from their order, from the dated
  id (0309) and from OpenRouter's endpoint name `x-ai/grok-4.20-20260309` (its record there was
  created on 2026-03-31).
- A second host of the same model, `https://docs.oracle.com/en-us/iaas/Content/generative-ai/xai-grok-4-20.htm`,
  prints "Knowledge Cutoff: Not available".
- Cutoff figures on third-party pages (September 2025 on one, November 2024 on another) disagree
  with each other and are **UNVERIFIED**; they are not used.

## 3. OpenRouter endpoints on 2026-10-01

Source for every row: `https://openrouter.ai/api/v1/models/<author>/<slug>/endpoints` (public;
it answered without a key although the API reference describes a bearer token). The `tag` column
is the slug to send in a provider preference. Prices are converted from per-token to per 1M
tokens. The API reference for the listing is
`https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints`.

- **Uptime** is the listing's one-day figure (`uptime_last_1d`: "successful requests /
  (successful + error requests) * 100", rate-limited requests excluded), as first read. At a
  later reading the same day no figure differed by more than 0.3 points.
- **Status.** The API reference lists the codes (0, -1, -2, -3, -5, -10) without describing
  them, and they moved within the day. Every endpoint below showed 0, except `nebius/fp8` (-5,
  gemma-3-27b) and `groq` (-2, gpt-oss-20b) at the first reading, and `novita/bf16` (-2,
  gemma-3-27b) and `siliconflow/fp8` (-2, gpt-oss-20b) at the later one. None of the four is a
  recommended endpoint; the six recommended endpoints showed 0 each time.
- **Discount.** The API reference describes `pricing.discount` as "Fractional discount applied
  to this endpoint's pricing; the price is multiplied by (1 - discount) (0 = no discount, 1 =
  free)". Two endpoints below carry one (`sambanova-turbo` and `streamlake`); every other
  endpoint shows 0.

**`meta-llama/llama-3.3-70b-instruct` (primary)** (created 2024-12-06; 11 endpoints; read twice)

| tag | quantization | context | $/1M in | $/1M out | uptime 1d |
|---|---|---|---|---|---|
| `deepinfra/turbo` | fp8 | 65,536 | 0.10 | 0.32 | 99.1 |
| `novita/bf16` | bf16 | 12,288 | 0.135 | 0.40 | 97.6 |
| `akashml/fp8` | fp8 | 131,072 | 0.20 | 0.52 | 99.4 |
| `parasail/fp8` | fp8 | 131,072 | 0.22 | 0.50 | 98.8 |
| `cloudflare/fp8` | fp8 | 24,000 | 0.293 | 2.253 | 98.7 |
| `sambanova-turbo` | unknown | 131,072 | 0.45 | 0.90 | 99.4 |
| `groq` | unknown | 131,072 | 0.59 | 0.79 | 99.8 |
| `coreweave/fp16` | fp16 | 128,000 | 0.71 | 0.71 | 99.6 |
| `google-vertex/us-central1` | unknown | 128,000 | 0.72 | 0.72 | not given |
| `google-vertex` | unknown | 128,000 | 0.72 | 0.72 | not given |
| `together` | unknown | 131,072 | 1.04 | 1.04 | 99.2 |

The `sambanova-turbo` row carries a discount of 0.25 in the listing; the other ten show 0.

DeepInfra's own page, `https://deepinfra.com/meta-llama/Llama-3.3-70B-Instruct-Turbo`, confirms
FP8, $0.10 / $0.32, a 65,536-token context and the Hugging Face repository
`meta-llama/Llama-3.3-70B-Instruct`.

**`deepseek/deepseek-chat` (primary)** (name "DeepSeek: DeepSeek V3"; created 2024-12-26; 2
endpoints; read twice)

| tag | quantization | context | $/1M in | $/1M out | uptime 1d | note |
|---|---|---|---|---|---|---|
| `streamlake` | unknown | 128,000 | 0.2574 | 1.0287 | 98.4 | the listing carries a discount of 0.1 |
| `deepinfra/fp4` | fp4 | 163,840 | 0.32 | 0.89 | 94.3 | |

The listed `streamlake` prices are the prices after the discount: they equal 0.286 and 1.143
less 10%, and OpenRouter's model page (`https://openrouter.ai/deepseek/deepseek-chat/providers`)
prints "$0.2574 / $1.029 per 1M" beside a mark of 10% off. The same arithmetic holds for the
`sambanova-turbo` row above (0.45 and 0.90 are 0.60 and 1.20 less 25%). When the discount ends
is not stated on any page read (**UNVERIFIED**). If it ends, the price of this endpoint rises to
about 0.286 / 1.143.

DeepInfra's own page, `https://deepinfra.com/deepseek-ai/DeepSeek-V3`, confirms the model id
`deepseek-ai/DeepSeek-V3`, fp4 and $0.32 / $0.89, and points to the Hugging Face repository
`deepseek-ai/DeepSeek-V3`. OpenRouter's page for the other host,
`https://openrouter.ai/provider/streamlake`, lists `deepseek/deepseek-chat` among the routes it
serves and says nothing about weights or precision.

**`qwen/qwen-2.5-7b-instruct`** (created 2024-10-16; 1 endpoint)

| tag | quantization | context | $/1M in | $/1M out | uptime 1d |
|---|---|---|---|---|---|
| `phala` | unknown | 32,768 | 0.10 | 0.20 | 100.0 |

**`google/gemma-3-27b-it`** (created 2025-03-12; 4 endpoints)

| tag | quantization | context | $/1M in | $/1M out | uptime 1d |
|---|---|---|---|---|---|
| `deepinfra/fp8` | fp8 | 131,072 | 0.08 | 0.16 | 99.7 |
| `parasail/fp8` | fp8 | 131,072 | 0.08 | 0.45 | 99.8 |
| `nebius/fp8` | fp8 | 110,000 | 0.10 | 0.30 | 87.1 |
| `novita/bf16` | bf16 | 98,304 | 0.119 | 0.20 | 81.5 |

DeepInfra's own page, `https://deepinfra.com/google/gemma-3-27b-it`, confirms fp8 and
$0.08 / $0.16.

**`openai/gpt-oss-20b`** (created 2025-08-05; 12 endpoints)

| tag | quantization | $/1M in | $/1M out | uptime 1d |
|---|---|---|---|---|
| `darkbloom/fp8` | fp8 | 0.018 | 0.09 | 99.8 |
| `akashml/fp4` | fp4 | 0.02 | 0.10 | 99.4 |
| `dekallm/bf16` | bf16 | 0.029 | 0.14 | 98.7 |
| `coreweave/fp4` | fp4 | 0.03 | 0.13 | 100.0 |
| `deepinfra/bf16` | bf16 | 0.03 | 0.14 | 100.0 |
| `parasail/fp4` | fp4 | 0.03 | 0.15 | 99.9 |
| `novita/fp4` | fp4 | 0.04 | 0.15 | 98.5 |
| `siliconflow/fp8` | fp8 | 0.04 | 0.18 | 92.1 |
| `amazon-bedrock/eu-west-1` | unknown | 0.07 | 0.15 | 99.7 |
| `amazon-bedrock` | unknown | 0.07 | 0.15 | 100.0 |
| `google-vertex/us-central1` | unknown | 0.07 | 0.25 | 98.1 |
| `groq` | unknown | 0.075 | 0.30 | 95.8 |

All twelve list a 131,072-token context. DeepInfra's own page,
`https://deepinfra.com/openai/gpt-oss-20b`, gives the precision as "bfloat16", the price as
$0.03 / $0.14, and repeats the maker's note "Native MXFP4 quantization: The models are trained
with native MXFP4 precision for the MoE layer". That is the format of the released files.

**`openai/gpt-4o-mini`** (created 2024-07-18; 3 endpoints, all 128,000-token context)

| tag | $/1M in | $/1M out |
|---|---|---|
| `openai` | 0.15 | 0.60 |
| `azure` | 0.15 | 0.60 |
| `azure/swedencentral` | 0.165 | 0.66 |

A dated route also exists: `openai/gpt-4o-mini-2024-07-18` ("OpenAI: GPT-4o-mini (2024-07-18)"),
served by `openai` at $0.15 / $0.60.

**Not used on OpenRouter.** Grok 4.20 is also listed there as `x-ai/grok-4.20` (endpoint name
`x-ai/grok-4.20-20260309`, provider xAI, $1.25 / $2.50 under 200k prompt tokens), which matches
the direct xAI price. The study calls xAI directly.

## 4. How a provider is pinned in the OpenRouter API

Documentation: `https://openrouter.ai/docs/features/provider-routing` (the provider-routing guide
also answers at `https://openrouter.ai/docs/guides/routing/provider-selection`), and the request
schema at
`https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request`.

The request body takes a `provider` object. The fields that matter here:

| Field | Type, default | Documented meaning |
|---|---|---|
| `order` | string[] | "List of provider slugs to try in order" |
| `allow_fallbacks` | boolean, `true` | "Whether to allow backup providers when the primary is unavailable" |
| `only` | string[] | "List of provider slugs to allow for this request" |
| `quantizations` | string[] | "List of quantization levels to filter by"; levels `int4`, `int8`, `fp4`, `mxfp4`, `nvfp4`, `fp6`, `fp8`, `mxfp8`, `fp16`, `bf16`, `fp32`, `unknown` |
| `require_parameters` | boolean, `false` | "Only use providers that support all parameters in your request" |

- **Default routing is not a pin.** With no `provider` object the router load-balances: "look at
  the lowest-cost candidates and select one weighted by inverse square of the price", and it
  falls back to other providers on failure. Every OpenRouter call of the earlier ladder runs was
  routed this way.
- **Variant slugs.** A base slug such as `deepinfra` "matches all endpoints for that provider";
  "to target a specific variant or region, use the full slug including the suffix" (the
  documentation's own example is `deepinfra/turbo`). The `tag` values in section 3 are these
  full slugs.
- **`order` alone is not a pin.** The API reference describes it as "An ordered list of provider
  slugs. The router will attempt to use the first provider in the subset of this list that
  supports your requested model, and fall back to the next if it is unavailable"; with
  fallbacks left on, providers outside the list are used when those in it fail.
- **Fallbacks off.** With `allow_fallbacks` false and the named provider unavailable, the
  request fails; it is not sent elsewhere. The API reference: "false: use only the
  primary/custom provider, and return the upstream error if it's unavailable."

The pin to send, shown for the first primary. It is the documented form for disabling fallbacks
(`order` together with `allow_fallbacks: false`; the documentation's own example names two
providers), here with one full endpoint slug in the list and with the quantization filter added
as a guard against a relabelled endpoint:

```json
{
  "model": "meta-llama/llama-3.3-70b-instruct",
  "messages": [{"role": "user", "content": "..."}],
  "temperature": 0,
  "provider": {
    "order": ["deepinfra/turbo"],
    "allow_fallbacks": false,
    "quantizations": ["fp8"]
  }
}
```

With the OpenAI-compatible client the object goes in `extra_body={"provider": {...}}`. For
`phala` and `openai`, which state no quantization, the `quantizations` field is left out.

What the router answers when the one listed endpoint does not pass the `quantizations` filter is
not documented (**UNVERIFIED**). An error is expected, since fallbacks are off; the cost trial
will show it.

**Checking which provider served a call.** The documented response schema has `model` ("Model
used for completion") and no top-level `provider` field. Two documented ways to read the
provider:

- the request header `X-OpenRouter-Metadata: enabled` (default `disabled`) adds an
  `openrouter_metadata` object to the response; its `endpoints.available` list gives a
  `model`, a `provider` and a `selected` flag for each endpoint considered, so the provider
  that served the call is the one of the entry whose flag is true;
- `GET /api/v1/generation?id=<response id>` returns `provider_name` ("Name of the provider that
  served the request") and `model`
  (`https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation`).

Whether live responses also carry an undocumented top-level `provider` string is **UNVERIFIED**;
the cost trial will show it.

All six recommended endpoints list `temperature` among their supported parameters, which is the
only sampling parameter `read.py` sends.

## 5. Which checkpoint `deepseek/deepseek-chat` serves

**Finding.** On OpenRouter, `deepseek/deepseek-chat` is the record of the December 2024 model
and has not followed DeepSeek's own alias. No dated OpenRouter id exists for it; the slug itself
is the pin, together with a provider pin.

Evidence at source:

- The record is named "DeepSeek: DeepSeek V3", created 2024-12-26, and both endpoints are named
  `deepseek/deepseek-chat-v3`. Asking the endpoint listing for `deepseek/deepseek-chat-v3`
  returns the same record.
- OpenRouter's model page, `https://openrouter.ai/deepseek/deepseek-chat/providers`, links
  "Model weights" to `https://huggingface.co/deepseek-ai/DeepSeek-V3`, gives the date
  "Dec 26, 2024" and prints no notice of removal.
- Later checkpoints have their own records and their own hosts:
  `deepseek/deepseek-chat-v3-0324` ("DeepSeek V3 0324", created 2025-03-24; `siliconflow/fp8`
  $0.25 / $1.00, `gmicloud/fp8` $0.29 / $1.14) and `deepseek/deepseek-chat-v3.1` ("DeepSeek
  V3.1", created 2025-08-21; seven endpoints).
- The first-party DeepSeek provider is not among the endpoints of `deepseek/deepseek-chat`. On
  DeepSeek's own API the name `deepseek-chat` was never a fixed checkpoint
  (`https://api-docs.deepseek.com/updates`): V3 on 2024-12-26, V3-0324 on 2025-03-24, V3.1 on
  2025-08-21, V3.1-Terminus on 2025-09-22, V3.2-Exp on 2025-09-29, V3.2 on 2025-12-01; from
  2026-04-24 it pointed to the non-thinking mode of `deepseek-v4-flash`, and the name was to be
  "discontinued in three months (2026-07-24)". The current price page
  (`https://api-docs.deepseek.com/quick_start/pricing`) no longer lists it. So the December 2024
  weights are reachable only through third-party hosts of the open weights.
- DeepInfra's own page for the model it serves under this route is `deepseek-ai/DeepSeek-V3`,
  and that Hugging Face repository holds only the weights uploaded on 2024-12-26 (section 2).

What remains **UNVERIFIED**:

- that the `streamlake` endpoint serves the December 2024 weights, and at what precision. Its
  listing says quantization "unknown", and no StreamLake documentation of the model was found;
- the revision hash of the weights at either host (neither states one);
- OpenRouter's `canonical_slug`, `hugging_face_id`, `knowledge_cutoff` and any
  `expiration_date` for the record. The API reference
  (`https://openrouter.ai/docs/api/api-reference/models/get-models`) documents these fields of
  the all-models listing (`/api/v1/models`), but at every attempt that listing answered this
  check with a short list in another format that has none of them. Nothing read today announces
  a removal of the route, but the field that would announce it ("The date after which the
  model may be removed") was not seen. A `knowledge_cutoff` there would be OpenRouter's figure,
  not the maker's, and would not change the word "bounded";
- whether a request may name `deepseek/deepseek-chat-v3` instead of `deepseek/deepseek-chat`,
  and which of the two the response echoes. No call was made; the earlier ladder runs passed the
  echo check with `deepseek/deepseek-chat`, so that id stays until the cost trial shows more.

**The owner's choice (DECISIONS 14).** Two endpoints, neither ideal:

| | `deepinfra/fp4` | `streamlake` |
|---|---|---|
| Checkpoint named at the host's own page | yes (`deepseek-ai/DeepSeek-V3`) | no page found |
| Precision | fp4, below the FP8 of the released weights | not stated |
| Price per 1M | 0.32 / 0.89 | 0.2574 / 1.0287 (the plan's price; it includes a 10% discount with no stated end) |
| One-day uptime on 2026-10-01 | 94.3 | 98.4 |

Recommended: `deepinfra/fp4`, because the checkpoint and the precision can both be stated and
checked, which is what the memorisation controls and the paper's model table need. Its uptime
has to be tried in the cost trial; with fallbacks off, a failed request is an error to retry,
not a silent switch. If the owner prefers `streamlake`, the plan must say that the precision is
not stated by the host.

## 6. Direct routes and prices

| Route | Source | Price per 1M (in / out) | Note |
|---|---|---|---|
| Google `gemini-3.8-flash` | `https://ai.google.dev/gemini-api/docs/pricing` (page updated 2026-10-01) | 0.75 / 3.75, output "including thinking tokens" | "through December 31, 2026"; **1.50 / 7.50 "starting January 1, 2027"** |
| xAI `grok-4.20-0309-non-reasoning` | `https://docs.x.ai/docs/models/grok-4.20-0309-non-reasoning` | 1.25 / 2.50 under 200k prompt tokens; 2.50 / 5.00 at or above | cached input 0.20 |
| OpenAI `gpt-4o-mini` (first-party list price, for comparison) | `https://developers.openai.com/api/docs/models/gpt-4o-mini` | 0.15 / 0.60 | equals the OpenRouter price |

OpenRouter, `https://openrouter.ai/pricing`: "Inference is billed at the provider's list price on
every plan"; buying credits carries a 5.5% fee on the standard plan. The fee is outside the
per-token prices and outside the plan's price of a call.

## 7. Notes

1. **Why DeepInfra for four of the six.** Its endpoints state a precision, its own model pages
   repeat the model id, precision and price (a second source for the pin), and one host for
   llama-3.3-70b, deepseek-v3, gemma-3-27b and gpt-oss-20b keeps the serving stack the same
   across them. qwen-2.5-7b has one endpoint, and gpt-4o-mini goes to its maker.
2. **Precision of the two primaries.** Neither recommended pin serves the precision of the
   released weights: llama-3.3-70b is released in BF16 and pinned at fp8; deepseek-v3 is released
   in FP8 and pinned at fp4. The paper's model table should print the precision.
   - Full-precision alternative for llama-3.3-70b: `novita/bf16` at $0.135 / $0.40, with a
     12,288-token context and 97.6% one-day uptime; or `coreweave/fp16` at $0.71 / $0.71.
   - There is no FP8 endpoint for the December 2024 DeepSeek-V3.
3. **The plan's prices are per model id, not per endpoint.** They are the prices OpenRouter's
   model list showed on 2026-09-28. Today each equals the price of one endpoint: `deepinfra/turbo`
   (llama-3.3-70b), `streamlake` (deepseek-v3), `phala` (qwen-2.5-7b), `parasail/fp8`
   (gemma-3-27b), `darkbloom/fp8` (gpt-oss-20b) and `openai` (gpt-4o-mini). For three models that
   is not the endpoint recommended here. Once a provider is pinned, the registered price has to
   be that endpoint's price, or the spend log misstates the spend.
4. **`azure` is left out for gpt-4o-mini** because a second host may apply its own content
   filtering; `openai` is the maker's endpoint.
5. **Reasoning.** gpt-oss-20b is a reasoning model on every endpoint; gemini-3.8-flash cannot
   switch thinking off ("'minimal' is not supported"). Both are billed as output, as section 4 of
   the plan already says.
6. **Names.** xAI's pages and OpenRouter now print the company as "SpaceXAI"; the API host and
   the model id are unchanged.
7. **Single points of failure.** qwen-2.5-7b has one endpoint and deepseek-v3 two. If a pinned
   endpoint is withdrawn during the runs, the run cannot finish on the registered route.

## 8. Consequences for PLAN.md

These refer to `PLAN.md` as it stood on disk on 1 October, after its section 4 gained the column
"Pinned endpoint, precision" and the bullets on prices, the provider pin and the cutoff rule.

**Section 4, the table.** Cell text in the plan's own form ("documented: month (source)" or
"bounded: release month"). All prices are those of the pinned endpoint, read 2026-10-01.

| Model | Released | Training cutoff | Pinned endpoint, precision | $/1M in | $/1M out |
|---|---|---|---|---|---|
| llama-3.3-70b | 2024-12 | documented: December 2023 (model card) | `deepinfra/turbo`, fp8 | 0.10 | 0.32 |
| deepseek-v3 | 2024-12 | bounded: December 2024 | `deepinfra/fp4`, fp4 | **0.32** | **0.89** |
| qwen-2.5-7b | **2024-09** | bounded: September 2024 | `phala`, precision not stated | 0.10 | 0.20 |
| gemma-3-27b | 2025-03 | documented: August 2024 (model card) | `deepinfra/fp8`, fp8 | 0.08 | **0.16** |
| gpt-oss-20b | 2025-08 | documented: June 2024 (model card) | `deepinfra/bf16`, bf16 | **0.03** | **0.14** |
| gpt-4o-mini | 2024-07 | documented: October 2023 (provider model page) | `openai`, not applicable | 0.15 | 0.60 |
| gemini-3.8-flash | 2026-09 | documented: March 2026 (model card; January 2025 in some domains) | direct | 0.75 | 3.75 |
| grok-4.20 | 2026-03 | bounded: March 2026 | direct | 1.25 | 2.50 |

- Bold marks a value that differs from the draft: the release month of qwen-2.5-7b (it was
  2024-10) and five prices of three models.
- **deepseek-v3, if the owner takes `streamlake` instead:** the cell reads "`streamlake`,
  precision not stated" and the prices are 0.2574 / 1.0287 (the draft's 0.257 / 1.029 to four
  decimals). They may rise if the discount ends (section 3).
- **gpt-4o-mini route.** Keep `openai/gpt-4o-mini`, pinned to `openai`. The alias leads to the
  only snapshot (`gpt-4o-mini-2024-07-18`), neither id is deprecated, and the earlier ladder
  run finished under the echo check with this id. The cell can name the snapshot beside the
  alias. The dated route `openai/gpt-4o-mini-2024-07-18` is an equivalent whose echo has not
  been seen. The route id is a registered fact, so taking the dated route is a choice to make
  before registration, not after the cost trial.
- **gemini-3.8-flash.** The price holds through 2026-12-31. The id has no dated snapshot.
- **grok-4.20.** The price holds for prompts under 200k tokens; a prompt of the study is one
  entry and at most ten examples.

**Section 4, the bullets.**

- **Prices.** Three models change price with the pin (deepseek-v3, gemma-3-27b, gpt-oss-20b),
  because the ladder file's price for each is the price of another endpoint (section 7,
  note 3). The retrieval date of all eight registered prices becomes 2026-10-01.
- **Provider pin.** The plan's wording (one named endpoint, fallbacks off, the serving provider
  stored with each call) is what section 4 of this note documents. The request fields are
  `provider.order`, `allow_fallbacks: false` and `quantizations`.
- **Why these primaries.** Three facts to state, since the present wording does not:
  - Only llama-3.3-70b has a documented cutoff (December 2023). deepseek-v3 is bounded by its
    release month (December 2024).
  - "At a stated precision" holds for `deepinfra/turbo` (fp8) and `deepinfra/fp4` (fp4). It
    does not hold if `streamlake` is taken.
  - Neither pin is the precision of the released weights (BF16 for llama-3.3-70b, FP8 for
    DeepSeek-V3), and the maker of DeepSeek-V3 no longer serves the December 2024 model.
- **The deepseek-v3 condition (DECISIONS 17).** The second half applies: the maker documents no
  cutoff, so every statement says "bounded". On the first half: no dated id exists, but the
  route is tied to the December 2024 weights by OpenRouter's record and by the host's own page
  (section 5), which is as far as a check without a call can go.

**Must a primary be replaced?** No.

- llama-3.3-70b meets the plan as written.
- deepseek-v3 has no documented cutoff, and DECISIONS 17 keeps it as a primary with the word
  "bounded". Its route does serve the December 2024 model as far as OpenRouter's and DeepInfra's
  own pages show.
- The remaining risk is supply (two endpoints, one of them at 94.3% one-day uptime). The plan
  already has the rule for it, in section 6: if a primary's confirmatory runs cannot be
  completed on its registered route, "its three tests are reported as not evaluable and stay in
  the family. No other model takes its place without an amendment made before any evaluation."
  Under that rule nothing has to be named now.
- If the owner would rather keep six evaluable tests, the candidate among the eight is
  gemma-3-27b: open weights, a documented cutoff (August 2024), four endpoints with a stated
  precision. It would have to be named in the registration, or in an amendment made before any
  evaluation, as the rule requires. This is the owner's decision; the rule itself still carries
  the owner-to-confirm tag.

**Section 3, post-cutoff slices.**

- Five cutoffs are documented and three are bounded by the release month (section 1).
- The plan takes slices inside the test split and reads no Late outcome in October (a rule it
  marks for the owner's confirmation). Under that rule gemini-3.8-flash and grok-4.20 (both
  March 2026) have no slice.
- The six remaining slices start after these days, which the counts-only code needs:
  2023-10-31 (gpt-4o-mini), 2023-12-31 (llama-3.3-70b), 2024-06-30 (gpt-oss-20b), 2024-08-31
  (gemma-3-27b), 2024-09-30 (qwen-2.5-7b) and 2024-12-31 (deepseek-v3). The qwen-2.5-7b date
  is one month earlier than the draft's release month implied.

**Section 9.**

- The registered prices are those of the table above.
- The estimates and the check of the caps were made at the draft's prices and have to be
  recomputed at the pinned ones (the harness's dry run prices the run sheet):
  - deepseek-v3: input +24%, output −13% (0.32 / 0.89 against 0.2574 / 1.0287);
  - gpt-oss-20b: input +67%, output +56% (0.03 / 0.14 against 0.018 / 0.09). It is a
    reasoning model with a $3 cap, so it is the row to look at;
  - gemma-3-27b: output −64% (0.16 against 0.45).
- The gemini-3.8-flash price doubles on 2027-01-01 (1.50 / 7.50), which matters for anything
  moved to January.
- OpenRouter's fee on buying credits (5.5% on the standard plan) is outside the price of a call
  and outside the spend the harness records. The plan should say whether the $200 cap is on
  list-price spend or on money paid.

**Sections 11 and 17.** The "Checkpoints" bullet of section 11 already has the wording of the
provider-pin bullet of section 4; nothing changes there. Section 17 records the hash of this
note; it is to be taken after the owner's choice for deepseek-v3 is written into section 5 and
the table above.

**Section 12 (Gate 1).** The fourth threshold's cutoff for llama-3.3-70b is confirmed as
December 2023; the constant in `corpus.py` needs no change.

## 9. Consequences for `read.py` (for its owner)

Values for the table of the eight readers (price date 2026-10-01 for every row):

| Model | Model id sent | Endpoint (`provider.order`) | `quantizations` | $/1M in | $/1M out |
|---|---|---|---|---|---|
| llama-3.3-70b | `meta-llama/llama-3.3-70b-instruct` | `deepinfra/turbo` | `fp8` | 0.10 | 0.32 |
| deepseek-v3 | `deepseek/deepseek-chat` | `deepinfra/fp4` (owner to confirm) | `fp4` | 0.32 | 0.89 |
| qwen-2.5-7b | `qwen/qwen-2.5-7b-instruct` | `phala` | left out | 0.10 | 0.20 |
| gemma-3-27b | `google/gemma-3-27b-it` | `deepinfra/fp8` | `fp8` | 0.08 | 0.16 |
| gpt-oss-20b | `openai/gpt-oss-20b` | `deepinfra/bf16` | `bf16` | 0.03 | 0.14 |
| gpt-4o-mini | `openai/gpt-4o-mini` | `openai` | left out | 0.15 | 0.60 |
| gemini-3.8-flash | `gemini-3.8-flash` | direct, no provider object | not applicable | 0.75 | 3.75 |
| grok-4.20 | `grok-4.20-0309-non-reasoning` | direct, no provider object | not applicable | 1.25 | 2.50 |

What the harness has to do with them:

- Send the `provider` object per OpenRouter model (section 4) with `allow_fallbacks: false`, in
  the endpoint's `extra_body`; nothing under `analysis/commitment/` changes.
- Refuse a live run for any model outside the table, and while a route is not set.
- Store the serving provider with every call (routing-metadata header, or the generation
  endpoint), and refuse a response from any other provider. In the routing metadata the
  provider that served the call is the one of the entry flagged `selected`; the other entries
  were considered and not used.
- As it stood on 1 October, `read.py` does these three: its table `ROUTES` holds the six
  OpenRouter rows as unset, with the endpoints above in its comments. The values above are
  what is entered when the routes are set; a price left out there keeps the ladder's price,
  which is wrong for deepseek-v3, gemma-3-27b and gpt-oss-20b.
- The exact strings to compare are not documented and are to be fixed in the cost trial: the
  routing metadata and the generation record name the provider ("DeepInfra", "Phala",
  "OpenAI" in the endpoint listing's `provider_name`), which is not the tag sent in `order`.
- The ladder's endpoints carry price dates of 2026-09-28 for the OpenRouter routes and
  2026-09-06 and 2026-09-07 for the two direct routes; the direct prices were read again today
  and are unchanged, so one date serves all eight.
- If the owner takes the dated slug `openai/gpt-4o-mini-2024-07-18` before registration
  (section 8), the accepted echo must be that id. What OpenRouter echoes for it has not been
  seen.
- With fallbacks off, an outage of the pinned endpoint returns an error. The harness should
  treat it as a failed attempt to retry later, never as a reason to change the route.
