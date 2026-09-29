# Related work, checked at source (COLING 2027 study)

Status: checked 2026-09-29 for *Estimated Recovery: TBD. How language models read forward-looking
estimates in operational notices, against human readers and what actually happened*. Nothing
here is registered. This file covers the works that the design memo (section 7) lists as
closest related work, plus those it marked "not yet verified". It is grouped by theme so that
each group can become one paragraph of the paper's related-work section.

**How each entry was checked.**

- Every page was fetched with curl, using the User-Agent
  `collie-research-fetch/0.1 (academic research; polite, cached)`, at least 1.2 s apart. No
  personal data was sent. Web search was used only to find URLs.
- Citation fields were copied from the page's own citation metadata (ACL Anthology, arXiv,
  PMLR, ICLR proceedings, Nature, OJS, AAAI). Where the publisher blocked our client, they were
  copied from the DOI registry record at Crossref.
- The "does" line comes from the abstract or the full text that was read, never from memory.
- Several sites returned 403 to our client: dblp (bot check), faa.gov, healthproductshortages.ca,
  escholarship.org and sciencedirect.com. Those facts were read from Wayback Machine captures or
  from registries (Crossref, OpenAlex, RePEc) instead, and each entry says which.
- The local cache of every page read is in the session scratchpad (`relverify/`), not in the
  repository.

**Status labels.**

- **VERIFIED:** the citation fields and the description were read at the source.
- **PARTLY VERIFIED:** the work exists as cited, but a field or a claim is confirmed only
  weakly. The entry says which.
- **UNVERIFIED:** could not be confirmed. Do not cite it as stated.

"We differ" describes the design as planned. It is not a result.

---

## 1. How language models read uncertainty and estimative language

- **Belém et al. 2024.** Catarina G Belém, Markelle Kelly, Mark Steyvers, Sameer Singh, Padhraic
  Smyth. 2024. Perceptions of Linguistic Uncertainty by Language Models and Humans. In
  *Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing*,
  pages 8467–8502. doi:10.18653/v1/2024.emnlp-main.483.
  - Opened: https://aclanthology.org/2024.emnlp-main.483/ (VERIFIED)
  - Does: maps uncertainty expressions ("probably", "highly unlikely") to numbers with 10 LMs.
    7 of the 10 match human population norms, but their readings shift with whether the
    statement is actually true.
  - We differ: our expressions are time hedges in real operational notices ("Estimated
    recovery: TBD", "early Q3"). Readings are scored against realised outcomes and a decision
    loss as well as against human readers.
- **Tang, Shen and Kejriwal 2026.** Zhisheng Tang, Ke Shen, Mayank Kejriwal. 2026. An evaluation
  of estimative uncertainty in large language models. *npj Complexity* 3, Article 8.
  doi:10.1038/s44260-026-00070-6. Online 2 February 2026. Preprint: arXiv:2405.15185.
  - Opened: https://www.nature.com/articles/s44260-026-00070-6,
    https://arxiv.org/abs/2405.15185, and the Crossref record (VERIFIED)
  - Does: compares LLM readings of words of estimative probability ("maybe", "probably not")
    with a human survey (Fagen-Ulmschneider). Models align for some words but not others, and
    diverge further under gendered and Chinese contexts.
  - We differ: the reference is what actually happened, not only a survey norm, and the words
    sit inside dated operational statements.
- **Petridis, Pelechrinis and Obradovic 2026.** Christos Petridis, Konstantinos Pelechrinis, Zoran
  Obradovic. 2026. How Unlikely Is "Unlikely"? Assessing Verbal Probability Perception Across
  Large Language Models. arXiv:2608.26327 (v1, 26 Aug 2026).
  - Opened: https://arxiv.org/abs/2608.26327 (VERIFIED)
  - Does: runs a word-to-number mapping task for 11 uncertainty expressions across 19 models,
    plus a roundtrip test. Models keep the human ordering, but read negative expressions
    ("unlikely", "improbable") too high.
  - We differ: we score against outcomes and use operational time estimates. It was posted less
    than three months before the 12 Oct 2026 deadline, so ARR treats it as contemporaneous:
    cite and discuss it, no detailed comparison needed.
- **Sileo and Moens 2023.** Damien Sileo, Marie Francine Moens. 2023. Probing neural language
  models for understanding of words of estimative probability. In *Proceedings of the 12th Joint
  Conference on Lexical and Computational Semantics (\*SEM 2023)*, pages 469–476.
  doi:10.18653/v1/2023.starsem-1.41.
  - Opened: https://aclanthology.org/2023.starsem-1.41/ (VERIFIED)
  - Does: tests whether LMs capture the consensual probability of words of estimative
    probability, using prompts built on the UNLI dataset and a new probabilistic-reasoning set.
    Both tasks are hard out of the box, and fine-tuning helps.
  - We differ: we test reading of hedged dates in real notices against realised outcomes, not
    consensus probability levels or logical composition.
- **Zhou, Jurafsky and Hashimoto 2023.** Kaitlyn Zhou, Dan Jurafsky, Tatsunori B. Hashimoto. 2023.
  Navigating the Grey Area: How Expressions of Uncertainty and Overconfidence Affect Language
  Models. In *Proceedings of the 2023 Conference on Empirical Methods in Natural Language
  Processing*, pages 5506–5524. doi:10.18653/v1/2023.emnlp-main.335.
  - Opened: https://aclanthology.org/2023.emnlp-main.335/ (VERIFIED)
  - Does: builds a typology of epistemic markers and injects 50 of them into QA prompts.
    Accuracy varies by more than 80%, and high-certainty markers lower accuracy by 7%.
  - We differ: the markers are in the source text being read, not in the prompt. We ask whether
    the extracted interval and certainty class follow the source's markers.
- **Tsvilodub et al. 2025.** Polina Tsvilodub, Kanishk Gandhi, Haoran Zhao, Jan-Philipp Fränken,
  Michael Franke, Noah D. Goodman. 2025. Non-literal Understanding of Number Words by Language
  Models. arXiv:2502.06204. The arXiv comment says "To appear in the Proceedings of CogSci 2025".
  - Opened: https://arxiv.org/abs/2502.06204. The eScholarship page returned 403 to our client.
    (PARTLY VERIFIED: the venue is confirmed only by the arXiv comment and a search hit at
    https://escholarship.org/uc/item/08c3s3jt.)
  - Does: compares LLM and human non-literal readings of number words (hyperbole, pragmatic
    halo) using Rational Speech Act models. RSA-inspired chain-of-thought prompting makes the
    models more human-like.
  - We differ: our imprecision is in operational dates and time windows, and we score it
    against what happened as well as against human readings.
- **Lovering et al. 2025.** Charles Lovering, Michael Krumdick, Viet Dac Lai, Varshini Reddy, Seth
  Ebner, Nilesh Kumar, Rik Koncel-Kedziorski, Chris Tanner. 2025. Language Model Probabilities
  are Not Calibrated in Numeric Contexts. In *Proceedings of the 63rd Annual Meeting of the
  Association for Computational Linguistics (Volume 1: Long Papers)*, pages 29218–29257.
  doi:10.18653/v1/2025.acl-long.1417.
  - Opened: https://aclanthology.org/2025.acl-long.1417/ (VERIFIED)
  - Does: shows that LM output probabilities are not calibrated to numeric information in the
    prompt, such as a fair coin, and are biased by word identity, order and frequency.
  - We differ: we use this as motivation. We elicit distributions by verbalised quantiles and
    by repeated samples rather than from token probabilities.
- **Owusu and Feldman 2026.** Hillary N. Owusu, Naomi Feldman. 2026. Anchoring Depends on
  Confidence and Post-Training in Language Models. In *Proceedings of the 64th Annual Meeting of
  the Association for Computational Linguistics (Volume 2: Short Papers)*, pages 174–180.
  doi:10.18653/v1/2026.acl-short.16.
  - Opened: https://aclanthology.org/2026.acl-short.16/ (VERIFIED)
  - Does: measures how irrelevant numerical primes shift LLM quantitative judgements. The effect
    falls with model confidence regardless of accuracy, and is stronger for high anchors.
  - We differ: our distractors are dates that occur naturally in notices (depletion,
    "available until", expiry), not injected primes.

*Draft paragraph.* Work on LLM readings of uncertainty compares models with human norms for
estimative words (Belém et al., 2024; Sileo and Moens, 2023; Tang et al., 2026; Petridis et al.,
2026), studies markers placed in prompts (Zhou et al., 2023), and studies non-literal number
words (Tsvilodub et al., 2025). We read hedged time estimates in real operational text, and
score the readings against human readers, against what happened, and by a decision loss.

## 2. Human meaning and calibration of estimative terms

- **Wallsten et al. 1986.** Thomas S. Wallsten, David V. Budescu, Amnon Rapoport, Rami Zwick,
  Barbara Forsyth. 1986. Measuring the vague meanings of probability terms. *Journal of
  Experimental Psychology: General* 115(4):348–365. doi:10.1037/0096-3445.115.4.348.
  - Opened: Crossref record and OpenAlex abstract for the DOI. The APA page was not opened.
    (VERIFIED from the DOI registry.)
  - Does: estimates membership functions over [0, 1] for probability terms ("doubtful",
    "probable", "likely") with a modified pair-comparison procedure, and tests them with
    conjoint measurement.
  - We differ: we take vague-term semantics into operational time estimates and compare human
    and model readings with realised outcomes.
- **Mandel and Barnes 2014.** David R. Mandel, Alan Barnes. 2014. Accuracy of forecasts in
  strategic intelligence. *Proceedings of the National Academy of Sciences* 111(30):10984–10989.
  doi:10.1073/pnas.1406138111.
  - Opened: Crossref record, including the abstract. (VERIFIED from the DOI registry.)
  - Does: scores over 1,500 strategic intelligence forecasts, covering about 6 years from one
    assessment unit, with standard accuracy measures. It finds high discrimination and
    calibration, and shows that transformations after the forecast can improve calibration.
  - We differ: we calibrate the issuer's stated dates and the readers' interpretations of them,
    rather than the analysts' own probabilities. Our readers are LLMs and humans, and we add a
    decision loss.

*Draft paragraph.* Vague probability terms have graded, measurable meanings (Wallsten et al.,
1986), and expert forecasts can be scored against outcomes (Mandel and Barnes, 2014). We connect
the two: what a reader takes an operational estimate to mean, and how often that reading holds.

## 3. Factuality, speaker commitment and hedging

- **FactBank.** Roser Saurí, James Pustejovsky. 2009. FactBank: a corpus annotated with event
  factuality. *Language Resources and Evaluation* 43(3):227–268. doi:10.1007/s10579-009-9089-9.
  - Opened: https://link.springer.com/article/10.1007/s10579-009-9089-9 and the Crossref record
    (VERIFIED)
  - Does: annotates whether events are presented as actual, non-occurring or uncertain, using a
    descriptive framework of factuality, as a layer on top of TimeBank.
  - We differ: our "certainty class" is a factuality-style label on forward-looking estimates,
    and we check it against later outcomes, which FactBank does not have.
- **CommitmentBank.** Marie-Catherine de Marneffe, Mandy Simons, Judith Tonhauser. 2019. The
  CommitmentBank: Investigating projection in naturally occurring discourse. *Proceedings of Sinn
  und Bedeutung* 23(2):107–124. doi:10.18148/sub/2019.v23i2.601.
  - Opened: https://ojs.ub.uni-konstanz.de/sub/index.php/sub/article/view/601 (VERIFIED)
  - Does: a corpus of naturally occurring discourses built to study when clausal complements
    under entailment-cancelling operators (negation, questions, modals, conditionals) project
    as speaker commitments.
  - We differ: we study commitment to a date in operational notices, and whether it holds. We
    call our label "certainty class", not "commitment".
- **ModaFact.** Marco Rovera, Serena Cristoforetti, Sara Tonelli. 2025. ModaFact: Multi-paradigm
  Evaluation for Joint Event Modality and Factuality Detection. In *Proceedings of the 31st
  International Conference on Computational Linguistics*, pages 6378–6396.
  - Opened: https://aclanthology.org/2025.coling-main.425/ (VERIFIED)
  - Does: an Italian resource with joint factuality and modality labels on event expressions,
    together with classifier comparisons.
  - We differ: we label English operational estimates and add realised outcomes and a cost.
- **CoNLL-2010 shared task.** Richárd Farkas, Veronika Vincze, György Móra, János Csirik, György
  Szarvas. 2010. The CoNLL-2010 Shared Task: Learning to Detect Hedges and their Scope in Natural
  Language Text. In *Proceedings of the Fourteenth Conference on Computational Natural Language
  Learning – Shared Task*, pages 1–12.
  - Opened: https://aclanthology.org/W10-3001/ and the PDF (VERIFIED)
  - Does: a shared task on detecting uncertainty cues and their scope, to separate factual from
    uncertain information for information extraction.
  - We differ: we go beyond detecting a hedge and ask what the hedged estimate means as an
    interval, and whether it comes true.
- **BioScope.** Two sources, both verified:
  - György Szarvas, Veronika Vincze, Richárd Farkas, János Csirik. 2008. The BioScope corpus:
    annotation for negation, uncertainty and their scope in biomedical texts. In *Proceedings of
    the Workshop on Current Trends in Biomedical Natural Language Processing*, pages 38–45.
    Opened: https://aclanthology.org/W08-0606/
  - Veronika Vincze, György Szarvas, Richárd Farkas, György Móra, János Csirik. 2008. The BioScope
    corpus: biomedical texts annotated for uncertainty, negation and their scopes. *BMC
    Bioinformatics* 9(Suppl 11):S9. doi:10.1186/1471-2105-9-S11-S9. Opened: Crossref record and
    OpenAlex abstract.
  - Does: annotates negation and speculation keywords and their scopes in more than 20,000
    biomedical sentences (clinical free text, full papers and abstracts), with two annotators
    and adjudication.
  - We differ: the domain is operational supply notices, and our target is a temporal
    interpretation with an observable outcome, not the scope of a cue.

*Draft paragraph.* Factuality and commitment resources (Saurí and Pustejovsky, 2009; de
Marneffe et al., 2019; Rovera et al., 2025) and hedge-detection work (Szarvas et al., 2008;
Vincze et al., 2008; Farkas et al., 2010) annotate how strongly a writer stands behind a
proposition. None of them can check that stance against the world. Forward-looking operational
estimates can be checked, because the outcome arrives later.

## 4. Temporal expressions and their normalisation

- **TimeML.** James Pustejovsky, José Castaño, Robert Ingria, Roser Saurí, Robert Gaizauskas,
  Andrea Setzer, Graham Katz, and Dragomir Radev. 2003. TimeML: Robust Specification of Event and
  Temporal Expressions in Text. In *New Directions in Question Answering: Papers from the 2003
  AAAI Spring Symposium*.
  - Opened:
    https://aaai.org/papers/0005-ss03-07-005-timeml-robust-specification-of-event-and-temporal-expressions-in-text/
    (VERIFIED, with one caveat)
  - Caveat: the AAAI page lists eight authors, including Radev, and gives no page numbers. Some
    secondary listings give seven authors. Use the AAAI list.
  - Does: a markup language that anchors events to time expressions, orders events, and allows
    delayed, underspecified interpretation of partly determined times.
- **ISO-TimeML.** James Pustejovsky, Kiyong Lee, Harry Bunt, Laurent Romary. 2010. ISO-TimeML: An
  International Standard for Semantic Annotation. In *Proceedings of the Seventh International
  Conference on Language Resources and Evaluation (LREC'10)*.
  - Opened: https://aclanthology.org/L10-1027/ (VERIFIED; the page gives no page numbers)
  - Does: a revised, interoperable TimeML, with an annotation meta-model that has a semantics.
  - We differ (TimeML family): TIMEX-style values are points or calendar units. We need an
    interval or a distribution, anchored to the statement date, with abstention, for expressions
    like "TBD", "early Q3" and "as it is released".
- **TempEval-3.** Naushad UzZaman, Héctor Llorens, Leon Derczynski, James Allen, Marc Verhagen,
  James Pustejovsky. 2013. SemEval-2013 Task 1: TempEval-3: Evaluating Time Expressions, Events,
  and Temporal Relations. In *Second Joint Conference on Lexical and Computational Semantics
  (\*SEM), Volume 2: Proceedings of the Seventh International Workshop on Semantic Evaluation
  (SemEval 2013)*, pages 1–9.
  - Opened: https://aclanthology.org/S13-2001/ and the PDF (VERIFIED)
  - Does: a shared task covering timex, event and temporal-relation extraction, with a larger
    dataset and single ranking measures.
  - We differ: evaluation is against outcomes and a decision loss, not only against gold TIMEX
    values.
- **HeidelTime.** Two sources, both verified:
  - Jannik Strötgen, Michael Gertz. 2010. HeidelTime: High Quality Rule-Based Extraction and
    Normalization of Temporal Expressions. In *Proceedings of the 5th International Workshop on
    Semantic Evaluation*, pages 321–324. Opened: https://aclanthology.org/S10-1071/ and the PDF.
  - Jannik Strötgen, Michael Gertz. Multilingual and cross-domain temporal tagging. *Language
    Resources and Evaluation* 47(2):269–298. doi:10.1007/s10579-012-9179-y. Crossref gives 8 May
    2012 as the issued (online) date. Opened: Crossref record.
  - Does: a rule-based temporal tagger, run as a UIMA component, with precision- and
    recall-optimised rule sets. In TempEval-2 it reached top extraction F-scores (86%) and the
    best normalisation accuracy (85%). The LRE paper extends it across languages and domains.
  - We differ: it is one of our rule baselines, with the document date set to Date of Update.
    We report its coverage for each form.
- **SUTime.** Angel Chang, Christopher D. Manning. 2012. SUTime: A library for recognizing and
  normalizing time expressions. In *Proceedings of the Eighth International Conference on
  Language Resources and Evaluation (LREC'12)*, pages 3735–3740.
  - Opened: https://aclanthology.org/L12-1122/ (VERIFIED)
  - Does: a deterministic, rule-based tagger in Stanford CoreNLP, evaluated on TempEval-2.
  - We differ: it is a rule baseline, used the same way as HeidelTime.
- **SCATE.** Two sources, both verified:
  - Steven Bethard, Jonathan Parker. 2016. A Semantically Compositional Annotation Scheme for Time
    Normalization. In *Proceedings of the Tenth International Conference on Language Resources and
    Evaluation (LREC'16)*, pages 3779–3786. Opened: https://aclanthology.org/L16-1599/
  - Egoitz Laparra, Dongfang Xu, Steven Bethard. 2018. From Characters to Time Intervals: New
    Paradigms for Evaluation and Neural Parsing of Time Normalizations. *Transactions of the
    Association for Computational Linguistics* 6:343–356. doi:10.1162/tacl_a_00025. Opened:
    https://aclanthology.org/Q18-1025/, its .bib, and the Crossref record, which confirm
    volume 6.
  - Does: represents time expressions as compositions of temporal operators, which covers
    expressions that TimeML cannot. The 2018 paper adds a neural parser and an interval-based
    scoring metric.
  - We differ: SCATE's interval semantics are the closest formal precedent for our targets. We
    add graded uncertainty (quantiles), abstention for TBD, and scoring against outcomes.
- **Gautam, Lange and Strötgen 2024.** Akash Kumar Gautam, Lukas Lange, Jannik Strötgen. 2024.
  Discourse-Aware In-Context Learning for Temporal Expression Normalization. In *Proceedings of
  the 2024 Conference of the North American Chapter of the Association for Computational
  Linguistics: Human Language Technologies (Volume 2: Short Papers)*, pages 306–315.
  doi:10.18653/v1/2024.naacl-short.27.
  - Opened: https://aclanthology.org/2024.naacl-short.27/ (VERIFIED)
  - Does: normalises temporal expressions with LLM in-context learning, using example selection
    and a window-based prompt. It is competitive with dedicated systems and gains most in
    non-standard settings.
  - We differ: our targets are intervals or distributions with abstention, and they are also
    scored against outcomes.
- **TRAVELER.** Svenja Kenneweg, Jörg Deigmöller, Philipp Cimiano, Julian Eggert. 2026. TRAVELER:
  A Benchmark for Evaluating Temporal Reasoning Across Vague, Implicit and Explicit References.
  *SN Computer Science* 7(5), Article 379. doi:10.1007/s42979-026-04973-y. Published 22 April
  2026. Preprint: arXiv:2505.01325.
  - Opened: https://arxiv.org/abs/2505.01325 and the Crossref record for the DOI. The Springer
    page was found by search but not opened. (VERIFIED)
  - Does: a synthetic QA benchmark of 3,300 questions over sets of household events, with
    explicit, implicit and vague references to the past. Answers for vague references come from
    Prolific surveys, and performance is lowest on the vague category.
  - We differ: our vague references are real and forward-looking, and they are read into
    intervals scored against outcomes, not answered by QA exact match.
- **Bhatia, Peyrard and Zhao 2025.** Gagan Bhatia, Maxime Peyrard, Wei Zhao. 2025. Date Fragments:
  A Hidden Bottleneck of Tokenization for Temporal Reasoning. In *Proceedings of the 2025
  Conference on Empirical Methods in Natural Language Processing*, pages 3201–3219.
  doi:10.18653/v1/2025.emnlp-main.159.
  - Opened: https://aclanthology.org/2025.emnlp-main.159/ (VERIFIED)
  - Does: defines a date fragmentation ratio for BPE tokenisers and releases DateAugBench, with
    6,500 examples across date resolution, format-invariance puzzles and date arithmetic.
    Fragmentation costs up to 10 points on uncommon dates.
  - We differ: surface date format is one factor in our minimal pairs. The paper is about
    tokenisation, not QA format robustness, so the memo's description should change.

*Draft paragraph.* Temporal annotation (Pustejovsky et al., 2003, 2010; UzZaman et al., 2013)
and rule-based normalisers (Strötgen and Gertz, 2010; Chang and Manning, 2012) map expressions to
calendar values. SCATE (Bethard and Parker, 2016; Laparra et al., 2018) introduced
compositional interval semantics. LLM normalisation (Gautam et al., 2024) and vague-reference
benchmarks (Kenneweg et al., 2026) evaluate against gold values. We evaluate forward-looking
readings against gold values, against outcomes and by a decision loss, with HeidelTime and SUTime
as frozen baselines.

## 5. Forecasting with language models, and text as forecast context

- **ForecastBench.** Ezra Karger, Houtan Bastani, Chen Yueh-Han, Zachary Jacobs, Danny Halawi,
  Fred Zhang, Philip E. Tetlock. 2025. ForecastBench: A Dynamic Benchmark of AI Forecasting
  Capabilities. In *International Conference on Learning Representations (ICLR 2025)*, pages
  93943–93980.
  - Opened:
    https://proceedings.iclr.cc/paper_files/paper/2025/hash/ea74e45a229dac70b5b63b28d8934db6-Abstract-Conference.html
    (VERIFIED)
  - Does: a dynamic benchmark of 1,000 questions about future events, updated regularly. Expert
    human forecasters beat the best LLM.
  - We differ: there the LLM is the forecaster. Here it reads a third party's estimate, and we
    separate reading error from the issuer's own error.
- **Context is Key.** Andrew Robert Williams, Arjun Ashok, Étienne Marcotte, Valentina
  Zantedeschi, Jithendaraa Subramanian, Roland Riachi, James Requeima, Alexandre Lacoste, Irina
  Rish, Nicolas Chapados, Alexandre Drouin. 2025. Context is Key: A Benchmark for Forecasting
  with Essential Textual Information. In *Proceedings of the 42nd International Conference on
  Machine Learning*, PMLR 267:66887–66944.
  - Opened: https://proceedings.mlr.press/v267/williams25a.html (VERIFIED)
  - Does: a time-series benchmark in which every task pairs the numbers with hand-crafted text
    context that the model must use to solve it.
  - We differ: our text is third-party, written by the issuer, and can be wrong. We compare it
    with text-free baselines and score it with a decision loss.
- **Band et al. 2024.** Neil Band, Xuechen Li, Tengyu Ma, Tatsunori Hashimoto. 2024. Linguistic
  Calibration of Long-Form Generations. In *Proceedings of the 41st International Conference on
  Machine Learning*, PMLR 235:2732–2778.
  - Opened: https://proceedings.mlr.press/v235/band24a.html (VERIFIED)
  - Does: defines linguistic calibration: the LM's text should let its reader make calibrated
    predictions. It trains Llama 2 7B toward this with SFT followed by RL.
  - We differ: in their setting the LM writes and the reader decides. We reverse the roles: the
    LM reads a human issuer's hedged statement.
- **Carletti et al. 2026.** Mattia Carletti, Edward Phillips, Fredrik K. Gustafsson, Patitapaban
  Palo, Lei Clifton, Danielle Belgrave, Xiao Gu, David A. Clifton. 2026. When Text and Numbers
  Disagree: Evidence Arbitration in Large Language Models. arXiv:2608.20116 (v1, 20 Aug 2026).
  - Opened: https://arxiv.org/abs/2608.20116 (VERIFIED)
  - Does: builds a controlled synthetic benchmark in which text and numbers from a latent risk
    trajectory conflict. Models show systematic text-versus-number preferences and follow
    recency more than reliability cues.
  - We differ: our data are real, not synthetic conflicts, and we score against outcomes. The
    memo's claim that "all conflicts are presented at once" is not in the abstract (UNVERIFIED).
    This is also contemporaneous for ARR.
- **Joren et al. 2025.** Hailey Joren, Jianyi Zhang, Chun-Sung Ferng, Da-Cheng Juan, Ankur Taly,
  Cyrus Rashtchian. 2025. Sufficient Context: A New Lens on Retrieval Augmented Generation
  Systems. In *International Conference on Learning Representations (ICLR 2025)*.
  arXiv:2411.06037.
  - Opened: https://mlanthology.org/iclr/2025/joren2025iclr-sufficient/,
    https://arxiv.org/abs/2411.06037 and https://iclr.cc/virtual/2025/poster/30092. Pages are
    not given on these pages. (VERIFIED)
  - Does: classifies whether retrieved context suffices to answer a query. Large models answer
    wrongly instead of abstaining when it does not, and guided abstention improves selective
    accuracy.
  - We differ: our abstention is per field, on notices that give no estimate ("TBD", "no
    estimated release date"), and false commitment there is a scored behaviour.

*Draft paragraph.* LLM forecasting benchmarks make the model the forecaster (Karger et al.,
2025) or give it truthful, hand-written context (Williams et al., 2025). Linguistic calibration
asks whether an LM's hedges help its reader (Band et al., 2024). Our LM is the reader of someone
else's forecast, whose track record can be measured.

## 6. Updating, stale information and interference

- **Yuan, Ding and Vlachos 2025.** Zhangdie Yuan, Zifeng Ding, Andreas Vlachos. Do Language
  Models Update their Forecasts with New Information? arXiv:2509.23936 (v1, 28 Sep 2025; v3,
  4 Sep 2026).
  - Opened: https://arxiv.org/abs/2509.23936 (VERIFIED; no venue on the arXiv page)
  - Does: EvolveCast tests whether LLMs revise forecasts when given evidence published after
    their cutoff, against human forecasters. Models move in the right direction but update too
    little, and their confidence is poorly calibrated.
  - We differ: we look at real revision threads, in which the issuer updates its own estimate,
    and whether readers track the latest statement. The memo groups this paper with "synthetic
    or Wikidata" work. It is neither: it uses post-cutoff evidence and human forecasters.
- **Wang and Sun 2025.** Chupei Wang, Jiaqiu Vince Sun. 2025. Unable to Forget: Proactive
  Interference Reveals Working Memory Limits in LLMs Beyond Context Length. arXiv:2506.08184. The
  arXiv comment says "Accepted at ICML 2025 Workshop on Long Context Foundation Models (ICFM)".
  - Opened: https://arxiv.org/abs/2506.08184 (VERIFIED; the workshop acceptance comes only from
    the arXiv comment)
  - Does: PI-LLM streams key-value updates and asks for the final values. Accuracy falls
    log-linearly toward zero as earlier values interfere.
  - We differ: stale-value uptake is measured on real notice histories, where the older value
    is a real earlier estimate.
- **Wallat, Nejdl and Sikdar 2026.** Jonas Wallat, Wolfgang Nejdl, Sandipan Sikdar. 2026. When
  Facts Change: Temporal Knowledge Conflict Resolution in LLMs. In *Findings of the Association
  for Computational Linguistics: ACL 2026*, pages 2154–2184. doi:10.18653/v1/2026.findings-acl.103.
  - Opened: https://aclanthology.org/2026.findings-acl.103/ (VERIFIED)
  - Does: WikiRecentChanges, built from Wikidata, tests conflicts between parametric memory and
    context for facts that changed after the cutoff. Models reason about the change but rarely
    act on it.
  - We differ: our changing "facts" are estimates, and the ground truth is the realised
    outcome.

## 7. Leakage and look-ahead bias

- **Glasserman and Lin 2023.** Paul Glasserman, Caden Lin. Assessing Look-Ahead Bias in Stock
  Return Predictions Generated By GPT Sentiment Analysis. arXiv:2309.17322 (v1, 29 Sep 2023).
  - Opened: https://arxiv.org/abs/2309.17322 (VERIFIED)
  - Added here: this paper is not in the memo, but it is the direct precedent for masking names.
  - Does: separates look-ahead bias from a "distraction effect" by removing company
    identifiers from news headlines. Inside the training window, anonymised headlines do
    better.
  - We differ: our E4 masks name, manufacturer, NDC and strength, and shifts dates by whole
    years. It also adds a probe that shows no notice at all, and post-cutoff slices.
- **Li, Shen, Tu and Zhou 2024.** Edward Li, Min Shen, Zhiyuan Tu, Dexin Zhou. The Promise and
  Peril of Generative AI: Evidence from GPT as Sell-Side Analysts. arXiv:2412.01069 (v1, 2 Dec
  2024; v2, 22 Oct 2025). Also on SSRN, doi:10.2139/ssrn.4480947 (Crossref).
  - Opened: https://arxiv.org/abs/2412.01069 and the v2 PDF (VERIFIED)
  - Does: studies GPT earnings forecasts after earnings releases. It is not a paper about a
    look-ahead method. It limits look-ahead bias by sampling 7,114 press releases in a two-year
    window around GPT-4 Turbo's knowledge cutoff (30 April 2023), and names the pre-cutoff
    advantage a "time-traveler's advantage".
  - We differ: we use the same design idea, a slice after each model's cutoff, but add probes
    and masking. The memo lists this as a look-ahead-bias paper, so cite it as an example of the
    design, not as a method.
- **Gao, Jiang and Yan 2025.** Zhenyu Gao, Wenxi Jiang, Yutong Yan. Detecting Lookahead Bias in
  LLM Forecasts. arXiv:2512.23847 (v1, 29 Dec 2025; v2, 12 Jun 2026). Also on SSRN,
  doi:10.2139/ssrn.5985277 (Crossref).
  - Opened: https://arxiv.org/abs/2512.23847 (VERIFIED)
  - Does: estimates a "Lookahead Propensity" from recall queries that give only a firm and a
    date. A positive interaction between that propensity and the forecast signals
    contamination, and the propensity collapses after the cutoff.
  - We differ: our no-notice probe is the same kind of test, applied to drug and date pairs. A
    model that beats the base rate on the probe is excluded from outcome claims on items from
    before its cutoff.

## 8. Forward-looking statements and forecast bias in finance

- **Li 2010.** Feng Li. 2010. The Information Content of Forward-Looking Statements in Corporate
  Filings—A Naïve Bayesian Machine Learning Approach. *Journal of Accounting Research*
  48(5):1049–1102. doi:10.1111/j.1475-679X.2010.00382.x.
  - Opened: Crossref record, including the abstract. (VERIFIED)
  - Does: classifies the tone of forward-looking statements in the MD&A sections of 10-K and
    10-Q filings with naive Bayes. Tone predicts future earnings, and the standard
    dictionaries do not.
  - We differ: we ask how a reader interprets a dated operational estimate and whether the date
    holds, not how tone predicts returns.
- **Rogers and Stocken 2005.** Jonathan L. Rogers, Phillip C. Stocken. 2005. Credibility of
  Management Forecasts. *The Accounting Review* 80(4):1233–1260. doi:10.2308/accr.2005.80.4.1233.
  - Opened: Crossref record, including the abstract. (VERIFIED)
  - Does: shows that managers bias their forecasts according to incentives (litigation, insider
    trading, financial distress, industry concentration) and how easily the market can detect
    it, and that the market's response takes the predictable bias into account.
  - We differ: it motivates condition (b), giving the issuer's track record in context. We
    ask whether LLM readers discount predictable issuer bias the way markets do.
- **Bozanic, Roulstone and Van Buskirk 2018.** Zahn Bozanic, Darren T. Roulstone, Andrew Van
  Buskirk. 2018. Management earnings forecasts and other forward-looking statements. *Journal of
  Accounting and Economics* 65(1):1–20. doi:10.1016/j.jacceco.2017.11.008.
  - Opened: the Crossref record, and https://econpapers.repec.org/RePEc:eee:jaecon:v:65:y:2018:i:1:p:1-20
    for the abstract. ScienceDirect returned 403. (VERIFIED)
  - Does: separates "forecast-like" from other forward-looking statements. The other statements
    also move investors and analysts, and firms issue them more when uncertainty is high.
  - We differ: FDA notices mix quantitative dates with non-quantitative estimates ("TBD", "as
    it is released"). We read both kinds and score both.
- **FinCall-Surprise.** Dong Shu, Yanguang Liu, Huopu Zhang, Mengnan Du. 2026. FinCall-Surprise:
  A Large Scale Multi-modal Benchmark for Earning Surprise Prediction. In *Proceedings of the
  64th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)*,
  pages 13357–13370. doi:10.18653/v1/2026.acl-long.610.
  - Opened: https://aclanthology.org/2026.acl-long.610/ (VERIFIED)
  - Does: a benchmark of 2,688 earnings calls (transcripts, audio, slides) for earnings-surprise
    prediction, run on 26 LLMs. High accuracy is often an artefact of class imbalance.
  - We differ: we take its lesson on imbalance. We report Brier scores with their components
    and the base rates, not accuracy.

*Draft paragraph.* Accounting research has long studied the content and bias of managers'
forward-looking statements (Rogers and Stocken, 2005; Li, 2010; Bozanic et al., 2018). We bring
the question to operational supply notices, and ask whether LLM readers discount an issuer's
predictable slip when its record is shown to them.

## 9. Drug shortages and other operational notices

- **Chicoine and Griffin 2025.** Noah Chicoine, Jacqueline Griffin. 2025. The unreliability of
  estimated release dates in hospital drug shortage management: A case study of hospital pharmacy
  operations during the COVID-19 pandemic. *PLOS One* 20(10): e0328747.
  doi:10.1371/journal.pone.0328747. Published 13 October 2025.
  - Opened: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0328747 (VERIFIED)
  - Does: analyses the estimated release dates (ERDs) in weekly wholesaler reports sent to one
    hospital from October 2022 to June 2023. ERDs are inaccurate and change unpredictably:
    - They changed 18.9% of the time from week to week.
    - When they changed, they moved later 71% of the time.
    - The data cannot be shared, because of an NDA between Northeastern University and the
      hospital. This is stated in the Data Availability statement.
  - We differ: we use public FDA text, measure outcomes by derived rules, and look at LLM
    reading. Reading "71% of revisions move later" as optimism is our interpretation; the paper
    says "unreliable".
- **ShortageSim.** Mingxuan Cui, Yilan Jiang, Duo Zhou, Cheng Qian, Yuji Zhang, Qiong Wang. 2026.
  ShortageSim: Simulating Drug Shortages Under Information Asymmetry. *Proceedings of the AAAI
  Conference on Artificial Intelligence* 40(45):38321–38330. doi:10.1609/aaai.v40i45.41172.
  Preprint: arXiv:2509.01813.
  - Opened: https://arxiv.org/abs/2509.01813, https://arxiv.org/html/2509.01813v3 and the
    Crossref record. The AAAI OJS page returned an unreadable compressed body. (VERIFIED)
  - Does: runs LLM agents, for manufacturers and buyers, that react to FDA shortage alerts.
    - The data come from 476 Wayback captures of the FDA list from January 2023 to August 2024.
    - It releases 2,925 FDA shortage reports and 51 resolved trajectories.
    - It reports closer alignment with the real trajectories than a zero-shot baseline.
  - We differ: we score how the text of the notices is read. We do not simulate, and our
    captures run from 2019 to 2026, with outcomes derived for each statement.
- **CHATATC.** Sinan Abdulhak, Wayne Hubbard, Karthik Gopalakrishnan, Max Z. Li. 2024. CHATATC:
  Large Language Model-Driven Conversational Agents for Supporting Strategic Air Traffic Flow
  Management. arXiv:2402.14850 (v2, 24 Jul 2024). The arXiv comment gives the venue as ICRAT, the
  11th International Conference on Research in Air Transportation.
  - Opened: https://arxiv.org/abs/2402.14850 (PARTLY VERIFIED: the ICRAT proceedings were not
    opened)
  - Does: trains an LLM on more than 80,000 Ground Delay Program issuances, revisions and
    cancellations from 2000 to 2023, and tests its question answering.
  - We differ (for E6): we read the estimative terms in FAA advisories and score them against
    the realised programmes.
- **FAA Order JO 7210.3 (terms).** *Facility Operation and Administration*, Order JO 7210.3EE.
  The archived index says "Effective: 1/22/26, Change: Change 2".
  - Opened: the Wayback captures of https://www.faa.gov/air_traffic/publications/atpubs/foa_html/
    listed below. faa.gov itself returned 403 to our client.

    | Page | Capture |
    |---|---|
    | Index | 20260611203558 |
    | chap18_section_13 | 20260103065935 |
    | chap18_section_10 | 20260114221305 |
    | chap18_section_5 | 20251025091100 |
    | chap18_section_7 | 20260618085541 |
    | chap18_section_21 | 20260203142342 |

  - Verified: paragraph 18-13-4 (National Ground Stops) requires every ATCSCC ground-stop
    advisory to include "Airport. Facilities Included. Expect Update Time. Reason. Probability of
    Extension. Remarks (Optional)."
  - UNVERIFIED: the levels of "Probability of Extension" (LOW, MEDIUM, MODERATE, HIGH) and the
    terms POSSIBLE, PROBABLE and EXPECTED are not defined in the five sections read: 18-5
    Coordination, 18-7 Traffic Management Initiatives, 18-10 Ground Delay Programs, 18-13
    Ground Stops, and 18-21 Operations Plan.
    - The section 18-13 capture (3 Jan 2026) predates Change 2 (22 Jan 2026).
    - Definitions may exist elsewhere, for example in ATCSCC procedures or the Pilot/Controller
      Glossary. Those were not checked.
    - Do not write that the FAA defines these levels until a source is found. The "stated
      definitions as a further reference" in E6 has no source yet.
- **Health Canada shortage reports (API fields and licence).** The site moved from
  drugshortagescanada.ca to Health Product Shortages Canada (healthproductshortages.ca) on
  18 January 2026, with an updated API.
  - Opened: https://www.canada.ca/en/health-canada/services/drugs-health-products/compliance-enforcement/establishment-licences/drug-establishment-licensing-bulletin/new-website-health-product-shortages.html
    (Drug Establishment Licensing Bulletin 193, 22 January 2026). healthproductshortages.ca
    returned 403 to our client, so it was read through Wayback captures:
    - The home page (20260626023500) and About & Resources (20260506003653).
    - The old API documentation, "Public API Access" at drugshortagescanada.ca/blog/52 (capture
      20240624175156), and "Public web API examples" at blog/61 (capture 20241112102356).
    - One report, healthproductshortages.ca/shortage/115404 (capture 20260506003842).
  - Verified, report page fields. These are page labels, not API keys:
    - Report ID, Drug Identification Number, Brand name, Common or Proper name, Company Name,
      Market Status, Active Ingredient(s), Strength(s), Dosage form(s), Route of administration,
      Packaging size, ATC code, ATC description.
    - Reason for shortage, Anticipated start date, Actual start date, **Estimated end date**,
      **Actual end date**, Shortage status, Updated date.
    - Company comments, Health Canada comments, Tier 3 Status.
    - A version history with separate English and French versions.
  - Verified, old API (drugshortagescanada.ca, documentation dated 2018-09-18):
    - Base URL `/api/v1`, a login that needs a verified account, and an `auth-token` header.
    - A limit of 1,000 requests per hour.
    - A `search` endpoint with parameters `orderby`, `order`, `filter_status` (resolved,
      anticipated_shortage, active_confirmed, avoided_shortage, discontinued), `term`, `din`,
      `report_id`, `limit` and `offset`.
    - Endpoints `shortages/{id}` and `discontinuances/{id}`.
    - The documentation recommends a monthly data extract for full downloads.
  - UNVERIFIED:
    - The JSON field names of a report object. The documentation does not list them.
    - The documentation of the new 2026 API. Blog pages 52 and 61 on the new site were not
      archived.
    - **Any licence or terms of use for the report data.** None of the pages read states one.
      Some related Health Canada datasets on open.canada.ca are said, in search results only,
      to be under the Open Government Licence – Canada. That does not establish the licence of
      the report database.
  - For January: a second jurisdiction looks feasible. It has an explicit "Estimated end date"
    against an "Actual end date", and bilingual versions. Confirm the licence with Health Canada
    before collecting.

*Draft paragraph.* Estimated release dates for drugs in shortage are known to be unreliable
(Chicoine and Griffin, 2025), on data that cannot be shared. FDA shortage histories rebuilt from
the Wayback Machine have been used to drive agent simulations (Cui et al., 2026). We release a
public, text-level resource: the statements themselves, paired with outcomes, human readings and
model readings.

## 10. Evaluation method and resource-paper precedents

- **Crystal et al. 2005.** Michael Crystal, Alex Baron, Katherine Godfrey, Linnea Micciulla,
  Yvette Tenney, Ralph Weischedel. 2005. A Methodology for Extrinsically Evaluating Information
  Extraction Performance. In *Proceedings of Human Language Technology Conference and Conference
  on Empirical Methods in Natural Language Processing*, pages 652–659.
  - Opened: https://aclanthology.org/H05-1082/ and the PDF (VERIFIED)
  - Does: evaluates IE extrinsically, through question answering. It "blends" machine and
    human-gold extraction databases in fixed proportions to estimate what better IE would buy.
  - We differ: E7 applies the same gold-blending idea one error class at a time, and prices
    reading errors in pinball loss and Brier score.
- **Reuver, Verberne and Fokkens 2024.** Myrthe Reuver, Suzan Verberne, Antske Fokkens. 2024.
  Investigating the Robustness of Modelling Decisions for Few-Shot Cross-Topic Stance Detection:
  A Preregistered Study. In *Proceedings of the 2024 Joint International Conference on
  Computational Linguistics, Language Resources and Evaluation (LREC-COLING 2024)*, pages
  9245–9260.
  - Opened: https://aclanthology.org/2024.lrec-main.809/ (VERIFIED)
  - Use: a precedent for preregistered hypotheses at a COLING-family venue.
- **CEHA.** Rui Bai, Di Lu, Shihao Ran, Elizabeth M. Olson, Hemank Lamba, Aoife Cahill, Joel
  Tetreault, Alejandro Jaimes. 2025. CEHA: A Dataset of Conflict Events in the Horn of Africa. In
  *Proceedings of the 31st International Conference on Computational Linguistics*, pages
  1475–1495.
  - Opened: https://aclanthology.org/2025.coling-main.99/ (VERIFIED)
  - Use: a COLING template for a small, expert-annotated resource of 500 event descriptions in
    a real-world domain.
- **SUMIE.** EunJeong Hwang, Yichao Zhou, Beliz Gunel, James Bradley Wendt, Sandeep Tata. 2025.
  SUMIE: A Synthetic Benchmark for Incremental Entity Summarization. In *Proceedings of the 31st
  International Conference on Computational Linguistics*, pages 10839–10864.
  - Opened: https://aclanthology.org/2025.coling-main.721/ (VERIFIED)
  - Use: a COLING precedent for incremental updating. It is fully synthetic, while ours uses
    real revision threads.
- **MaintIE.** Tyler K. Bikaun, Tim French, Michael Stewart, Wei Liu, Melinda Hodkiewicz. 2024.
  MaintIE: A Fine-Grained Annotation Schema and Benchmark for Information Extraction from
  Maintenance Short Texts. In *Proceedings of the 2024 Joint International Conference on
  Computational Linguistics, Language Resources and Evaluation (LREC-COLING 2024)*, pages
  10939–10951.
  - Opened: https://aclanthology.org/2024.lrec-main.954/ (VERIFIED)
  - Use: a template for an operational short-text resource. It has 1,076 annotated maintenance
    texts, with several annotators.
- **Strong and Vlachos 2025 (TSVer).** Marek Strong, Andreas Vlachos. 2025. TSVer: A Benchmark for
  Fact Verification Against Time-Series Evidence. In *Proceedings of the 2025 Conference on
  Empirical Methods in Natural Language Processing*, pages 29906–29926.
  doi:10.18653/v1/2025.emnlp-main.1519.
  - Opened: https://aclanthology.org/2025.emnlp-main.1519/ (VERIFIED)
  - Does: verifies 304 real claims from 41 fact-checkers against 400 time series.
  - We differ: TSVer's claims look back and the evidence already exists. Ours look forward,
    and the evidence, the outcome, arrives later.

---

## Could not verify, and what to do

| Item | What is missing | Action |
|---|---|---|
| FAA estimative terms (LOW/MEDIUM/MODERATE/HIGH; POSSIBLE/PROBABLE/EXPECTED) | No definition in five sections of JO 7210.3EE; only the field "Probability of Extension" is required (18-13-4) | Check the ATCSCC procedures and the Pilot/Controller Glossary; until then, describe the terms as the issuer's own vocabulary with no stated definition |
| Health Canada report-data licence | No licence or terms on any page read | Ask Health Canada, or cite only the pages, before any January collection |
| Health Canada API JSON fields; the new 2026 API documentation | Old documentation lists parameters only; new pages not archived and the live site is 403 to our client | Read the new documentation in a browser, or ask |
| Carletti et al.: "all conflicts presented at once" | Not in the abstract | Drop the phrase, or read the paper |
| Tsvilodub et al.: CogSci 2025 volume and pages | eScholarship 403; only the arXiv comment | Open in a browser |
| CHATATC: ICRAT proceedings | Only the arXiv comment | Cite as arXiv |
| TimeML page numbers | Not on the AAAI page | Cite without pages |

## Corrections to the design memo (section 7 and its "not yet verified" list)

1. **Bhatia et al. 2025** is about date tokenisation (the fragmentation ratio and DateAugBench),
   not "format robustness in QA".
2. **Owusu and Feldman 2026** studies anchoring on irrelevant numerical primes, not on "free
   estimates".
3. **Yuan, Ding and Vlachos 2025** (EvolveCast) uses real post-cutoff evidence and human
   forecasters. It is not synthetic or Wikidata data. Of the three papers the memo groups
   together, only Wallat et al. use Wikidata.
4. **ShortageSim** is AAAI 2026 (40(45):38321–38330). It used 476 Wayback captures (January
   2023 to August 2024) and releases both 2,925 reports and 51 resolved trajectories.
5. **Chicoine and Griffin 2025**: the data are weekly wholesaler ERD reports (October 2022 to
   June 2023) under an NDA, as the memo says. The paper says "unreliable" and reports 71% of
   revisions moving later. "Optimism" is our reading of that number, so say so.
6. **TRAVELER** is now published: SN Computer Science 7(5):379, 2026.
7. **Tang et al.** is npj Complexity 3, Article 8 (2026), doi:10.1038/s44260-026-00070-6.
8. **arXiv 2412.01069** is a paper about GPT as a sell-side analyst that uses a sample around the
   cutoff. It is not a method for detecting look-ahead bias. The detection method is
   **2512.23847**, and **Glasserman and Lin (arXiv 2309.17322)** is the precedent for masking
   names. It has been added.
9. **TimeML** (AAAI 2003) lists eight authors, including Radev.
10. **Gautam et al. 2024**: the abstract says "temporal expression normalization". "TIMEX3 point
    normalisation" is not in the abstract, so rephrase.
11. **Petridis et al.** (26 Aug 2026) and **Carletti et al.** (20 Aug 2026) are contemporaneous
    under ARR's three-month rule: cite and discuss, no detailed comparison required.
