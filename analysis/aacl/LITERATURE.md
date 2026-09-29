# Follow-up at an ACL-family venue: literature and venue notes

Research notes, 2026-09-29, from a web sweep in which every cited work was checked at its source
(arXiv, ACL Anthology, DOI landing page or publisher) by a second reader; only works confirmed to
exist are listed, with the verifier's corrected fields. Venue facts were read on the official
pages named next to them. Nothing here is registered, and nothing is a claim of the UV paper.

Two corrections to the notes below, from the repository: the magnitude label `medium` is the
templates' hidden analysis label (`alert_spec.magnitude_bin`), not text the model sees, and the
comparison with the provisional truth bins measures a label mismatch, not calibration
(`prereg/deviations.md`, 2026-09-28, finding 2); and every family-4 unit moves to a lead of 3,
so the true lead-time shift is two periods from a baseline lead of 1 and one from 2
(`analysis/commitment/PLAN.md`, DA8).

---


Checks run on 2026-09-29. Only items the verifier marked `exists=true` are cited, using the verifier's corrected fields. I also checked a few facts in this repo and give their paths. No files were modified.

---

## 1. Venue facts

### 1.1 Verified (official pages)

1. **AACL-IJCNLP 2026 exists.** It is the 5th AACL and 15th IJCNLP, held in Hengqin, China, November 6–10, 2026. https://2026.aaclnet.org/calls/main_conference_papers/ and https://2026.aaclnet.org/
2. **AACL 2026 is closed.** Submission was through ARR only (the May 2026 cycle or an earlier one):
   - ARR deadline: May 25, 2026.
   - Commitment deadline: August 7 (moved from August 2), with a second round August 18–25.
   - Notification: September 7. Camera-ready: September 30, 2026.
   - Commitment went through the OpenReview group `aclweb.org/AACL-IJCNLP/2026/Conference`.
   - Source: https://2026.aaclnet.org/calls/main_conference_papers/
3. **The ARR venue table was never updated for the AACL 2026 extension.** It still lists AACL 2026 with commitment on August 2, 2026. https://aclrollingreview.org/dates
4. **ARR cycles left in 2026.** Source: https://aclrollingreview.org/dates
   - August cycle: submission August 3 (passed), meta-reviews October 8, cycle end October 11.
   - October cycle: submission **October 12, 2026**, reviewer registration October 14, author response November 24–30, meta-reviews December 17, cycle end December 20.
   - No 2027 cycle has a date. ARR says it generally runs five cycles a year and sets each deadline individually.
5. **Which venues each cycle feeds.** Source: https://aclrollingreview.org/dates
   - EACL 2027: August cycle, commitment October 11, 2026.
   - NAACL 2027 and COLING 2027: October 12 cycle, commitment December 23, 2026.
   - ACL 2027: listed only as "January, 2027".
   - **No AACL 2027 appears in the table.**
6. **NAACL 2027** is in San Francisco, June 1–5, 2027, with commitment on December 23, 2026. A paper may be committed to only one primary venue. https://2027.naacl.org/calls/main_conference_papers/
7. **ARR "sustainable reviewing" applies from the October 2026 cycle.** Source: https://aclrollingreview.org/sustainable-reviewing-2026
   - Each submission must name a qualified service contributor (at most 2 submissions per contributor), or it goes into a lottery.
   - Every author needs a complete OpenReview profile with an ORCID.
   - Caps per cycle: 20 submissions per author, 5 as first or joint-first author.
8. **Dual submission and overlap.** ARR will not consider a paper that "overlaps significantly in content or results with papers that will be (or have been) published elsewhere, without exception". This covers refereed archival conferences. https://aclrollingreview.org/cfp
9. **Originality.** Source: https://aclrollingreview.org/cfp
   - Re-used text may be at most 10% of tokens.
   - "There can be no overlap in stated contributions."
   - Concurrent related submissions must cite each other.
   - Self-plagiarism (significant overlap with the authors' own publications) is a desk-rejection reason.
10. **Self-citations must be anonymous**, written in the third person ("Smith previously showed…"). https://aclrollingreview.org/cfp
11. **Preprints.** Since February 15, 2024 there is no anonymity period, and non-anonymous preprints may be posted at any time. Authors declare the preprint status on the submission form. Choosing the binding "no non-anonymous preprint" option means not preprinting until meta-reviews are released. https://aclrollingreview.org/cfp and https://aclrollingreview.org/anonymity and https://www.aclweb.org/adminwiki/images/5/56/ACL_Anonymity_Policy.pdf
12. **ARR's "preprint" question covers anything that reveals the authors' names, not only arXiv.** https://aclrollingreview.org/authors
13. **AACL-IJCNLP 2026 has a Findings track**, and every Findings paper must be presented. https://2026.aaclnet.org/registration/
14. **aaclnet.org lists no 2027 edition.** Its latest call for bids is for 2026. https://aaclnet.org/

### 1.2 Medium confidence (the pages were fetched by WebFetch because curl was blocked; re-check the wording in a browser)

- **ACL Publication Ethics.** Source: https://www.aclweb.org/adminwiki/index.php/ACL_Policy_on_Publication_Ethics
  - Authors must disclose similar prior publications, state very clearly how the new work differs, and cite them anonymously.
  - Overlap with works "published anywhere" is capped at 10% of tokens, and only the authors' own preprints are exempt. A refereed IEEE paper is therefore not exempt.
  - All prior publications must be disclosed, and venue chairs may grant exemptions.
- **ACL Policies for Review and Citation.** Source: https://www.aclweb.org/adminwiki/index.php/ACL_Policies_for_Review_and_Citation
  - The old anonymity-period text applies only to deadlines before January 12, 2024.
  - In February 2025 ACL approved five ARR cycles a year and an experiment with Findings decisions made inside ARR.

### 1.3 Implications (my reading, not official)

- **"AACL" is not a target that can be met right now.** AACL 2026 is closed and no 2027 edition is announced.
- **Concrete ACL-family options:**
  - The ARR October 12, 2026 cycle, leading to NAACL 2027 or COLING 2027.
  - The January 2027 cycle, leading to ACL 2027 (no date published yet).
- **October 12 is tight.** It is 13 days away and three days before the UV 2026 camera-ready (due 2026-10-15 per the project notes). It is only realistic if the informative-alert study has already been run. The January cycle is the sober default.
- **The UV paper will be a refereed archival IEEE paper**, so all of the following apply:
  - Certify-then-hedge, its theorems and its results cannot be stated as contributions again.
  - Text reused from UV counts against the 10% cap.
  - UV must be cited in the third person, disclosed on the form, and its differences stated.
  - Because the published UV paper reveals the authors' names, the preprint answer on the ARR form should be treated as "non-anonymous version exists" (see 1.4).
- **The UV paper already reports several things the follow-up planned** (repo: `paper/sections/08_results.tex`, `paper/sections/02_background.tex`, `paper/sections/11_limitations.tex`):
  - A 21-model ladder (all 21 run), with first-proposal family and direction accuracy from 0 to 65 of 96 shocked episodes, and commitment and accuracy moving together (post hoc r = 0.86).
  - False alerts on null twins, and an unreliable-alert condition (overstated, ambiguous or distractor).
  - A content-free control.
  - The magnitude "label mismatch".

  The follow-up's ladder, error and false-alert results must therefore be new analyses on new data (the informative-alert bank), not re-reports.

### 1.4 Unverified or open

- Whether an AACL 2027 (or IJCNLP-AACL 2027) will be held, and when.
- The exact date of the January 2027 ARR deadline.
- There is no numeric threshold for "significant overlap in content or results". Whether a text-grounded extension counts as distinct is a judgment for the editors or area chair.
- The exact adminwiki wording (see 1.2).
- Inconsistencies between official pages:
  - ARR gives the AACL commitment date as August 2; the AACL site gives August 7 plus a round ending August 25.
  - The sustainable-reviewing blog says "NAACL and COLING 2026"; other pages say 2027.
  - October meta-reviews are December 17 on ARR's page and December 18 on the NAACL page.
- Whether the OpenReview submission form has a specific field for a related published IEEE paper. The form was not inspected.
- Past "Findings of IJCNLP-AACL" volumes were not checked in the ACL Anthology.

---

## 2. Literature by strand

Fields are the verifier's corrected ones. "(in bib)" means the work is already in `paper/citations.bib`. A work cited in full in one strand is cited by short name plus URL in later strands.

### 2.1 Operational and supply-chain text (ops-text)

1. **SHIELD.** Zhi-Qi Cheng, Yifei Dong, Aike Shi, Wei Liu, Yuzhi Hu, Jason O'Connor, Alexander G. Hauptmann, Kate Whitefoot (2024). "SHIELD: LLM-Driven Schema Induction for Predictive Analytics in EV Battery Supply Chain Disruptions." Proc. EMNLP 2024: Industry Track, Miami, pp. 303–333. DOI 10.18653/v1/2024.emnlp-industry.24. https://aclanthology.org/2024.emnlp-industry.24/
   - How the follow-up differs: SHIELD induces event schemas from 12,070 news and report paragraphs and predicts disruptions. It has no quantitative typed shock, no order decision, and no check against later operational data. It is the closest ACL-family precedent.
2. **Shahsavari et al.** Maryam Shahsavari, Omar Khadeer Hussain, Morteza Saberi, Pankaj Sharma (2024). "Event Identification for Supply Chain Risk Management Through News Analysis by Using Large Language Models." The Review of Socionetwork Strategies 18(2):255–278. DOI 10.1007/s12626-024-00169-z. https://link.springer.com/article/10.1007/s12626-024-00169-z
   - How the follow-up differs: the paper labels news as relevant or not to a named event (per the verifier, detection rather than structured extraction). It extracts no magnitude or timing.
3. **AlMahri et al., agentic monitoring.** Sara AlMahri, Liming Xu, Alexandra Brintrup (2026). "Automating Supply Chain Disruption Monitoring via an Agentic AI Approach." arXiv:2601.09680 (preprint; SSRN version DOI 10.2139/ssrn.5317578). https://arxiv.org/abs/2601.09680
   - How the follow-up differs: this is a seven-agent pipeline from news to mitigation, with F1 of 0.962–0.991 on 30 synthesised scenarios. It scores detection and mapping, not whether acting on the reading pays off or whether later data confirms it.
4. **Foresight Learning.** Benjamin Turtel, Paul Wilczewski, Kris Skotheim (2026). "Forecasting Supply Chain Disruptions with Foresight Learning." arXiv:2604.01298 (preprint). https://arxiv.org/abs/2604.01298
   - How the follow-up differs: it gives calibrated probabilities of an aggregate disruption from news, trained on realised outcomes. It has no per-alert quantity (magnitude or lead-time size) and no inventory decision. It is the most direct comparator for calibration.
5. **Davoodi et al.** Laleh Davoodi, Filip Ginter, Sima Salimi, Harri Lorentz (2026). "Large Language Models for Risk Detection in E-commerce: Reliability, Semantic Alignment, and Managerial Insights." SN Computer Science 7(6), art. 645. DOI 10.1007/s42979-026-05213-z. https://link.springer.com/article/10.1007/s42979-026-05213-z
   - How the follow-up differs: it does multi-label risk classification on 121 annotated articles. Its evidence of label over-generation is relevant to false alerts, but it has no quantities and no outcomes.
6. **Zhang et al.** Lanxin Zhang, Xin Sun, Mao Xu, Yuyao Yang, Tingting Zhang, Zongguo Wen (2026). "Large language model-driven analysis of supply risk dynamics in global electric vehicle supply chain." Environmental Impact Assessment Review 119, art. 108378. DOI 10.1016/j.eiar.2026.108378. https://www.sciencedirect.com/science/article/abs/pii/S0195925526000521
   - How the follow-up differs: this is a descriptive taxonomy (2,843 events, 50 event types, 8 risk types). It is useful for grounding alert families and error categories, but it measures neither reading accuracy nor decisions.
7. **Wichmann et al.** Pascal Wichmann, Alexandra Brintrup, Simon Baker, Philip Woodall, Duncan McFarlane (2020). "Extracting supply chain maps from news articles using deep neural networks." International Journal of Production Research 58(17):5320–5336. DOI 10.1080/00207543.2020.1720925. https://doi.org/10.1080/00207543.2020.1720925
   - How the follow-up differs: it extracts buyer–supplier structure, not shocks. It is the pre-LLM anchor for this strand.
8. **Janjua et al.** Naeem Khalid Janjua, Falak Nawaz, Daniel D. Prior (online 2021; issue 2023). "A fuzzy supply chain risk assessment approach using real-time disruption event data from Twitter." Enterprise Information Systems 17(4), art. 1959652. DOI 10.1080/17517575.2021.1959652. https://www.tandfonline.com/doi/abs/10.1080/17517575.2021.1959652
   - How the follow-up differs: it maps short, noisy text to a fuzzy risk score. It has no typed quantities and no verification against later data.
9. **CrudeOilNews.** Meisin Lee, Lay-Ki Soon, Eu Gene Siew, Ly Fie Sugianto (2022). "CrudeOilNews: An Annotated Crude Oil News Corpus for Event Extraction." Proc. LREC 2022, Marseille, pp. 465–479. https://aclanthology.org/2022.lrec-1.49/ (arXiv:2204.03871)
   - How the follow-up differs: it annotates supply and demand shock event types with arguments, but has no decision or outcome link. It is a template for releasing an alert-to-ShockSpec corpus.
   - Spelling: the two verifiers disagreed on the third author's name. I fetched the Anthology BibTeX, which has "Eu Gene Siew". arXiv hyphenates it.
10. **NOTAM-Evolve.** Maoqi Liu, Quan Fang, Yuhao Wu, Can Zhao, Yang Yang, Kaiquan Cai (2026). "NOTAM-Evolve: A Knowledge-Guided Self-Evolving Optimization Framework with LLMs for NOTAM Interpretation." Proc. AAAI-26 40(1):764–772. DOI 10.1609/aaai.v40i1.37043. https://ojs.aaai.org/index.php/AAAI/article/view/37043
    - How the follow-up differs: it parses short operational alerts into structured fields, with a 10k expert-annotated benchmark. It is the nearest "short alert to typed spec" analogue, but it has no downstream decision and no outcome check.
    - Companion dataset paper "Knots": Advanced Engineering Informatics 69, art. 104086, DOI 10.1016/j.aei.2025.104086, https://doi.org/10.1016/j.aei.2025.104086. Its full title was not recorded.

Also verified, lower priority:
- Chu, Park, Kremer (Gül E. Kremer) 2020, Advanced Engineering Informatics 45:101053. https://doi.org/10.1016/j.aei.2020.101053
- AlMahri, Xu, Brintrup 2025, IJPR 64(6):2178–2209. https://doi.org/10.1080/00207543.2025.2575841
- Sui, Wang, Zheng 2024, Transportation Research Part E 189:103651. https://doi.org/10.1016/j.tre.2024.103651. Its text is Clarksons' market commentary reports, not news.

Strand gap (searcher): there is no peer-reviewed work on LLMs reading supplier lead-time change notices. The only examples found are vendor products, such as the Dynamics 365 procurement agent: https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-overview

### 2.2 LLMs in inventory and OR decisions (llm-ops)

1. **Ask, Clarify, Optimize.** Yaqi Duan, Yichun Hu, Jiashuo Jiang (2025). "Ask, Clarify, Optimize: Human-LLM Agent Collaboration for Smarter Inventory Control." arXiv:2601.00121 (preprint). https://arxiv.org/abs/2601.00121
   - How the follow-up differs: here the LLM elicits parameters and a solver decides, and the paper concludes that the bottleneck is "computational rather than informational". The follow-up studies the opposite regime, where the information is in the text and reading is the bottleneck. This is the key framing foil.
2. **Dynamics of Cognitive Heterogeneity.** Jiuyun Jiang, Yuecheng Hong, Bo Yang, Jin Yang, Guangxin Jiang, Xiaomeng Guo, Guang Xiao (2026). "Dynamics of Cognitive Heterogeneity: Investigating Behavioral Biases in Multi-Stage Supply Chains with LLM-Based Simulation." Proc. ACL 2026 (Vol. 1: Long Papers), pp. 19316–19333. DOI 10.18653/v1/2026.acl-long.882. https://aclanthology.org/2026.acl-long.882/
   - How the follow-up differs: LLM agents act as Beer Game players and there are no text alerts. It shows that ACL main accepts LLM-for-supply-chain work. The "bullwhip" wording was not confirmed from the abstract.
3. **SupChain-Bench.** Shengyue Guan, Yihao Liu, Lang Cao (2026). "SupChain-Bench: Benchmarking Large Language Models for Real-World Supply Chain Management." Findings of ACL 2026, pp. 7526–7550. DOI 10.18653/v1/2026.findings-acl.371. https://aclanthology.org/2026.findings-acl.371/
   - How the follow-up differs: it tests domain knowledge and SOP-grounded tool use. It does not test quantitative reading of alerts or verify anything against outcomes.
4. **Long et al.** Carol Xuan Long, David Simchi-Levi, Feng Zhu, Huangyuan Su, Andre P. Calmon, Flavio P. Calmon (2026). "Reliability and Effectiveness of Autonomous AI Agents in Supply Chain Management." arXiv:2605.17036 (v4). https://arxiv.org/abs/2605.17036
   - How the follow-up differs: the agents order directly, and the paper documents "agent bullwhip" and tail costs, which motivate bounded commitment. It has no text alerts.
5. **SabreAgent.** Yang Liu, Yulin Huang, Xue Yu, Jiong Dong, Jianshen Zhang, Yongzhi Qi (2026). "SabreAgent: Language Models at Design Time for Lost-Sales Inventory Control." arXiv:2609.19760. https://arxiv.org/abs/2609.19760
   - How the follow-up differs: the LLM is used only at design time and the OR core carries the gain on InventoryBench. The follow-up's claim is that text arriving at run time carries information no design-time policy can have.
6. **AIM-Bench.** Xuhua Zhao, Yuxuan Xie, Caihua Chen, Yuxiang Sun (2025). "AIM-Bench: Evaluating Decision-making Biases of Agentic LLM as Inventory Manager." arXiv:2508.11416. https://arxiv.org/abs/2508.11416
   - How the follow-up differs: it measures biases in LLM ordering. The follow-up keeps the LLM out of the order computation.
7. **Large Language Newsvendor.** Jifei Liu, Zhi Chen, Yuanguang Zhong (2025). "Large Language Newsvendor: Decision Biases and Cognitive Mechanisms." arXiv:2512.12552. https://arxiv.org/abs/2512.12552
   - How the follow-up differs: its finding that biases persist even when the optimal formula is given supports the split between reader and compiler.
8. **Chen et al.** Yang Chen, Samuel N. Kirshner, Anton Ovchinnikov, Meena Andiappan, Tracy Jenkin (2025). "A Manager and an AI Walk into a Bar: Does ChatGPT Make Biased Decisions Like We Do?" MSOM 27(2):354–368. DOI 10.1287/msom.2023.0279. https://doi.org/10.1287/msom.2023.0279
   - How the follow-up differs: it is peer-reviewed evidence of LLM decision biases, but it has no setting where the text carries information.
9. **OptiGuide.** Beibin Li, Konstantina Mellou, Bo Zhang, Jeevan Pathuri, Ishai Menache (2023). "Large Language Models for Supply Chain Optimization." arXiv:2307.03875. https://arxiv.org/abs/2307.03875
   - How the follow-up differs: the LLM is an interface that turns user what-if queries into solver code. The paper demonstrates it on a Microsoft cloud server-placement scenario; "deployed" is not confirmed. Its inputs are user queries, not exogenous alerts, and there is no statistical check.
10. **Jannelli et al.** Valeria Jannelli, Stefan Schöpf, Matthias Bickel, Torbjørn Netland, Alexandra Brintrup (2025). "Agentic LLMs in the supply chain: towards autonomous multi-agent consensus-seeking." IJPR, online 21 December 2025, pp. 1–31 (no volume or issue yet). DOI 10.1080/00207543.2025.2604311. https://doi.org/10.1080/00207543.2025.2604311
    - How the follow-up differs: the agents negotiate orders directly. The claim that they reduce bullwhip was not confirmed from the abstract.

Also verified:
- Simchi-Levi, Mellou, Menache, Pathuri 2026, in *AI in Supply Chains* (eds. Cohen, Dai), Springer, pp. 93–104. https://doi.org/10.1007/978-3-032-07054-8_7
- OptiMUS, Ahmaditeshnizi, Gao, Udell 2024, ICML, PMLR 235:577–596. https://proceedings.mlr.press/v235/ahmaditeshnizi24a.html
- ORLM, Huang et al. 2025, Operations Research 73(6):2986–3009. https://doi.org/10.1287/opre.2024.1233
- Yang, Baxi, Zhang, Jasin, Lei, Liu, Pakiman 2026. https://arxiv.org/abs/2609.08071

Already in the bib and not re-verified in this pass: InventoryBench https://arxiv.org/abs/2602.12631, InvAgent https://arxiv.org/abs/2407.11384, InvEvolve https://arxiv.org/abs/2605.00369, LLM-SAA https://arxiv.org/abs/2602.06357, STOCKTAKE https://arxiv.org/abs/2607.13618, EventCast https://arxiv.org/abs/2602.07695, InstructMPC https://arxiv.org/abs/2504.05946, MABIM https://arxiv.org/abs/2306.07542, llm-or-algorithms https://arxiv.org/abs/2608.27296.

### 2.3 E-values, anytime-valid testing and guarantees for LLM outputs (evalues-llm)

1. **Richter et al.** Leo Richter, Xuanli He, Pasquale Minervini, Matt J. Kusner (2025). "An Auditing Test To Detect Behavioral Shift in Language Models." ICLR 2025. https://arxiv.org/abs/2410.19406 (OpenReview h0jdAboh0o)
   - How the follow-up differs: it uses testing by betting to compare two models' generations. COLLIE tests the model's claim about the world against telemetry instead.
2. **Chen and Wang.** Can Chen, Jun-Kun Wang (2025). "Online Detection of LLM-Generated Texts via Sequential Hypothesis Testing by Betting." ICML 2025, PMLR 267:9231–9276. https://proceedings.mlr.press/v267/chen25bn.html
   - How the follow-up differs: its e-process runs on a stream of texts. In COLLIE the text is a prior and the e-process runs on numeric telemetry.
3. **E-valuator (in bib).** Shuvom Sadhuka, Drew Prinster, Clara Fannjiang, Gabriele Scalia, Bonnie Berger, Aviv Regev, Hanchen Wang (2025). "E-valuator: Reliable Agent Verifiers with Sequential Hypothesis Testing." arXiv:2512.03109. https://arxiv.org/abs/2512.03109
   - How the follow-up differs: it builds e-processes over verifier scores on agent trajectories. It has no model-named hypothesis and no external telemetry.
4. **CSA (in bib).** Hamed Khosravi, Xiaoming Huo (2026). "Conformal Selective Acting: Anytime-Valid Risk Control for RLVR-Trained LLMs." arXiv:2605.20270. https://arxiv.org/abs/2605.20270
   - How the follow-up differs: it controls the risk of the LLM's own actions. The follow-up verifies a claim the LLM read from text.
5. **Online Safety Monitoring.** Mona Schirmer, Metod Jazbec, Alexander Timans, Christian Naesseth, Maja Waldron, Eric Nalisnick (2026). "Online Safety Monitoring for LLMs." arXiv:2607.02510 (ICML 2026 Hypothesis Testing Workshop, non-archival). https://arxiv.org/abs/2607.02510
   - How the follow-up differs: it is a counterpoint. Simple thresholds calibrated by conformal risk control or UCB are competitive with e-valuator and detect failures *earlier*. Expect a reviewer to cite it.
6. **BB-EDGE.** Hongfu Gao, Songxin Zhang, Zejian Xie, Bingyi Jing, Zhou Wang, Yiming Liu (2026). "Anytime-Valid LLM Leaderboards via Benchmark-weighted and Block-Factorized e-Processes." arXiv:2609.32248 (posted 2026-09-26). https://arxiv.org/abs/2609.32248
   - How the follow-up differs: it is a tool, not a competitor. It gives anytime-valid, family-wise controlled comparisons that could be used across the 21-model ladder.
7. **Campos et al. survey.** Margarida Campos, António Farinhas, Chrysoula Zerva, Mário A. T. Figueiredo, André F. T. Martins (2024). "Conformal Prediction for Natural Language Processing: A Survey." TACL 12:1497–1516. DOI 10.1162/tacl_a_00715. https://aclanthology.org/2024.tacl-1.82/
   - How the follow-up differs: guarantees in ACL venues are mostly batch and conformal, and sequential, telemetry-verified guarantees are largely absent.
8. **Li et al.** Jiawei Li, Akshayaa Magesh, Venugopal Veeravalli (2026). "Principled Detection of Hallucinations in Large Language Models via Multiple Testing." Findings of ACL 2026, pp. 34132–34145. DOI 10.18653/v1/2026.findings-acl.1705. https://aclanthology.org/2026.findings-acl.1705/
   - How the follow-up differs: it is an ACL-family example of error-controlled checks on LLM outputs, but batch and with no downstream decision.
9. **Gligorić et al.** Kristina Gligorić, Tijana Zrnic, Cinoo Lee, Emmanuel Candès, Dan Jurafsky (2025). "Can Unconfident LLM Annotations Be Used for Confident Conclusions?" NAACL 2025 (Long), pp. 3514–3533. DOI 10.18653/v1/2025.naacl-long.179. https://aclanthology.org/2025.naacl-long.179/
   - How the follow-up differs: it gets valid inference from LLM text annotations plus a few human labels. The analogy is text as a prior that data then corrects. It is useful for a small human-labelled real-text validation.
10. **Mohri and Hashimoto.** Christopher Mohri, Tatsunori Hashimoto (2024). "Language Models with Conformal Factuality Guarantees." ICML 2024, PMLR 235:36029–36047. https://proceedings.mlr.press/v235/mohri24a.html
    - How the follow-up differs: it certifies the *text output* by making it less specific. The follow-up certifies the *decision* sequentially.

Also verified:
- Cherian, Gibbs, Candès 2024, NeurIPS 37, pp. 114812–114842. https://proceedings.neurips.cc/paper_files/paper/2024/hash/d02ff1aeaa5c268dc34790dd1ad21526-Abstract-Conference.html
- Quach, Fisch, Schuster, Yala, Sohn, Jaakkola, Barzilay 2024, ICLR. https://arxiv.org/abs/2306.10193
- Gui, Jin, Ren 2024, NeurIPS 37, pp. 73884–73919. https://proceedings.neurips.cc/paper_files/paper/2024/hash/870ccde24673d3970a680bb48496ed63-Abstract-Conference.html
- Ren et al. (KnowNo) 2023, CoRL, PMLR 229:661–682. https://proceedings.mlr.press/v229/ren23a.html
- Ota, Iwase, Ichihara, Komiyama, Imaizumi 2026 (CITE). https://arxiv.org/abs/2605.05873

### 2.4 Real-text datasets with outcomes (datasets); section 4 assesses how well they fit

1. **ShortageSim.** Mingxuan Cui, Yilan Jiang, Duo Zhou, Cheng Qian, Yuji Zhang, Qiong Wang (2026). "ShortageSim: Simulating Drug Shortages Under Information Asymmetry." Proc. AAAI-26 40(45):38321–38330. DOI 10.1609/aaai.v40i45.41172. https://ojs.aaai.org/index.php/AAAI/article/view/41172 (arXiv:2509.01813)
   - How the follow-up differs: its agents react to FDA announcements and are scored on resolution lag. It does not score quantitative reading.
2. **openFDA Drug Shortages endpoint** (`/drug/shortages.json`), U.S. FDA. Coverage "2012 to null"; the launch date is unsure; updated daily; CC0 1.0 "unless otherwise noted". https://open.fda.gov/apis/drug/drugshortages/
   - Related study: Md Raisul Islam Khan, Abdullah Al Mamun, Muhtasib Sarker Tahsin (2026). "Human-in-the-loop artificial intelligence for drug-shortage recurrence-risk ranking and synthetic inventory-policy simulation using U.S. Food and Drug Administration Data." Discover Artificial Intelligence 6, art. 1080. https://doi.org/10.1007/s44163-026-02144-9
   - How the follow-up differs: it is raw notices with no reading task defined.
3. **Foresight Learning evaluation set:** Turtel et al. 2026 (see 2.1). https://huggingface.co/datasets/LightningRodLabs/supply-chain-predictions (452 examples, no licence stated).
4. **IMF PortWatch.** International Monetary Fund with the University of Oxford (2023). "Disruptions" dataset, plus "Daily Port Activity Data and Trade Estimates". https://portwatch.imf.org/datasets/d9b37bf4b2104c85aebdcc0c1d8a2ab7_0/about. Licence: IMF terms https://www.imf.org/external/terms.htm plus GDACS terms https://www.gdacs.org/About/termofuse.aspx
   - How the follow-up differs: its alerts are structured, not text.
5. **LLM4Delay.** Thaweerath Phisannupawong, Joshua Julian Damanik, Han-Lim Choi (2025). "LLM4Delay: Flight Delay Prediction via Cross-Modality Adaptation of Large Language Models and Aircraft Trajectory Representation." arXiv:2510.23636. https://arxiv.org/abs/2510.23636. Data: https://huggingface.co/datasets/petchthwr/ICNDelay (MIT tag).
   - How the follow-up differs: it predicts delay end to end and has no typed reading.
6. **Time-MMD.** Haoxin Liu, Shangqing Xu, Zhiyuan Zhao, Lingkai Kong, Harshavardhan Kamarthi, Aditya B. Sasanur, Megha Sharma, Jiaming Cui, Qingsong Wen, Chao Zhang, B. Aditya Prakash (2024). "Time-MMD: Multi-Domain Multimodal Dataset for Time Series Analysis." NeurIPS 37 Datasets and Benchmarks, pp. 77888–77933. DOI 10.52202/079017-2476. https://proceedings.neurips.cc/paper_files/paper/2024/hash/8e7768122f3eeec6d77cd2b424b72413-Abstract-Datasets_and_Benchmarks_Track.html
   - How the follow-up differs: its reports are aligned to weekly or monthly series, not to alerts.
7. **TimesX.** Haoxin Liu, Yichen Zhou, Rajat Sen, B. Aditya Prakash, Abhimanyu Das (2026). "Rethinking Multimodal Time-Series Forecasting Evaluation." ICML 2026 (PMLR pages not confirmed). https://arxiv.org/abs/2607.06973
   - How the follow-up differs: it is a leakage protocol (post-cutoff windows), and no data release was found.
8. **From News to Forecast.** Xinlei Wang, Maike Feng, Jing Qiu, Jinjin Gu, Junhua Zhao (2024). "From News to Forecast: Integrating Event Analysis in LLM-Based Time Series Forecasting with Reflection." NeurIPS 37, pp. 58118–58153. DOI 10.52202/079017-1853. https://proceedings.neurips.cc/paper_files/paper/2024/hash/6aef8bffb372096ee73d98da30119f89-Abstract-Conference.html
   - How the follow-up differs: it fuses news into a forecaster and has no typed shock or verification.
9. **LEAF.** Mingtian Tan, Mihir Parmar, Palash Goyal, et al. (8 authors) (2026). "LEAF: A Living Benchmark for Event-Augmented Forecasting." arXiv:2605.16358. https://arxiv.org/abs/2605.16358
   - How the follow-up differs: it provides a protocol for checking publication time. Its 0%-to-92% case is a *leaked future* event, not a stale alert.
10. **Balashankar et al.** Ananth Balashankar, Lakshminarayanan Subramanian, Samuel P. Fraiberger (2023). "Predicting food crises using news streams." Science Advances 9(9), eabm3449. https://doi.org/10.1126/sciadv.abm3449
    - How the follow-up differs: it is evidence that text can warn up to 12 months ahead. Its corpus is not shared.

Also verified:
- NSW-EPNews, Bi, Huang, Jin, Zeng, Chen 2025. https://arxiv.org/abs/2506.11050
- Heeyoung Lee, Mihai Surdeanu, Bill MacCartney, Dan Jurafsky 2014, LREC'14, pp. 1170–1175. https://aclanthology.org/L14-1048/
- EDT: Zhihan Zhou, Liqian Ma, Han Liu 2021, Findings of ACL-IJCNLP 2021, pp. 2114–2124, DOI 10.18653/v1/2021.findings-acl.186. https://aclanthology.org/2021.findings-acl.186/
- CrudeOilNews (see 2.1).
- Context is Key (see 2.5).

### 2.5 The value of text for forecasting and decisions (text-value)

1. **Context is Key (CiK).** Andrew Robert Williams, Arjun Ashok, Étienne Marcotte, Valentina Zantedeschi, Jithendaraa Subramanian, Roland Riachi, James Requeima, Alexandre Lacoste, Irina Rish, Nicolas Chapados, Alexandre Drouin (2025). "Context is Key: A Benchmark for Forecasting with Essential Textual Information." ICML 2025, PMLR 267:66887–66944. https://proceedings.mlr.press/v267/williams25a.html (arXiv:2410.18959; code Apache-2.0)
   - How the follow-up differs: CiK scores forecast error (RCRPS) given hand-written context, and some tasks include distractor text. It has no typed extraction, no decision cost and no verification. It is the closest competitor on the claim that "text carries information the series lacks".
2. **Beyond Naïve Prompting.** Arjun Ashok, Andrew Robert Williams, Vincent Zhihao Zheng, Irina Rish, Nicolas Chapados, Étienne Marcotte, Valentina Zantedeschi, Alexandre Drouin (2026). "Beyond Naïve Prompting: Strategies for Improved Context-aided Forecasting with LLMs." TMLR 2026. https://arxiv.org/abs/2508.09904 (OpenReview https://openreview.net/forum?id=dkjHHFJkVI)
   - How the follow-up differs: it finds an "execution gap", where LLMs can explain how the context should change a forecast but fail to apply it. A typed ShockSpec plus a compiler is a direct response: the model reads and the compiler executes. This is a strong hook.
3. **Zhang et al.** Xiyuan Zhang, Boran Han, Haoyang Fang, et al. (15 authors in the TMLR version) (2026). "When Does Multimodality Lead to Better Time Series Forecasting?" TMLR 2026. https://arxiv.org/abs/2506.21611 (OpenReview https://openreview.net/forum?id=RggcWYWR3N)
   - How the follow-up differs: it finds that text helps only when it carries signal beyond the series. The follow-up builds exactly that condition, but must show that it holds rather than assume it.
4. **CAF-7M.** Vincent Zhihao Zheng, Étienne Marcotte, Arjun Ashok, Andrew Robert Williams, Lijun Sun, Alexandre Drouin, Valentina Zantedeschi (2026). "Overcoming the Modality Gap in Context-Aided Forecasting." ICML 2026 (PMLR pages not confirmed). https://arxiv.org/abs/2603.12451 (OpenReview https://openreview.net/forum?id=NOHlqCnYot)
   - How the follow-up differs: it argues that contexts must be "verifiably complementary" to the series. Use it to justify the informative stratum. It covers forecasting only, with no decisions.
5. **What If TSF.** Jinkwan Jang, Hyunbin Jin, Hyungjin Park, Kyubyung Chae, Taesup Kim (2026). "What If TSF: Reframing Time Series Forecasting as Scenario-Guided Multimodal Forecasting." arXiv:2601.08509 (v2, under review). https://arxiv.org/abs/2601.08509
   - How the follow-up differs: it tests counterfactual scenario text and finds that factual accuracy does not carry over to alternative scenarios. It is the closest design to a false or counterfactual alert test, but it has no verification that limits the damage.
6. **Merrill et al.** Mike A. Merrill, Mingtian Tan, Vinayak Gupta, Thomas Hartvigsen, Tim Althoff (2024). "Language Models Still Struggle to Zero-shot Reason about Time Series." Findings of EMNLP 2024, pp. 3512–3533. DOI 10.18653/v1/2024.findings-emnlp.201. https://aclanthology.org/2024.findings-emnlp.201/
   - How the follow-up differs: this ACL-family paper finds modest gains from context. The follow-up has the LLM read, not forecast.
7. **LLM Processes.** James Requeima, John Bronskill, Dami Choi, Richard E. Turner, David Duvenaud (2024). "LLM Processes: Numerical Predictive Distributions Conditioned on Natural Language." NeurIPS 2024. https://arxiv.org/abs/2405.12856
   - How the follow-up differs: it turns text directly into a numeric prior. In the follow-up the text weights a fixed typed hypothesis set that telemetry then checks. It is a natural baseline.
8. **Corroboration Illusion.** Yuan Lu, Yukuan Zhang (2026). "The Corroboration Illusion: When More News Makes LLM Forecasts Less True." arXiv:2609.22246. https://arxiv.org/abs/2609.22246
   - How the follow-up differs: it shows that injected LLM-written news flips 56% of forecasts with one article and 69–73% with five. This is the false-alert threat model. It has no mechanism that bounds the damage.
9. **GSM-DC.** Minglai Yang, Ethan Huang, Liang Zhang, Mihai Surdeanu, William Yang Wang, Liangming Pan (2025). "How Is LLM Reasoning Distracted by Irrelevant Context? An Analysis Using a Controlled Benchmark." EMNLP 2025, pp. 13329–13347. DOI 10.18653/v1/2025.emnlp-main.674. https://aclanthology.org/2025.emnlp-main.674/
   - How the follow-up differs: it is an ACL template for injecting controlled distractors, applied here to arithmetic rather than operational alerts.
10. **GSM-IC.** Freda Shi, Xinyun Chen, Kanishka Misra, Nathan Scales, David Dohan, Ed Chi, Nathanael Schärli, Denny Zhou (2023). "Large Language Models Can Be Easily Distracted by Irrelevant Context." ICML 2023, PMLR 202:31210–31227. https://proceedings.mlr.press/v202/shi23a.html
    - How the follow-up differs: it is the canonical distractor result on numeric reasoning.

Also verified:
- Andrews, Mengaldo 2026, mutual-information metrics for when text informs. https://arxiv.org/abs/2609.11282
- DeLLMa: Ollie Liu, Deqing Fu, Dani Yogatama, Willie Neiswanger 2025, ICLR 2025 Spotlight. https://arxiv.org/abs/2402.02392
- Berdica, Acero, Ipsen, Zehtabi, Cashmore, Veloso 2026, RLC 2026 per arXiv. https://arxiv.org/abs/2604.05859
- LLMForecaster: Zhang, Arvin, Efimov, Mahoney, Perrault-Joncas, Ramasubramanian, Wilson, Wolff 2024, NeurIPS 2024 TSALM workshop (non-archival). https://arxiv.org/abs/2412.02525

---

## 3. Positioning

**What the follow-up can claim.** Within these searches, I found no published work with all four of the following:
- (a) short operational alert text that states order-relevant quantities (magnitude, onset, lead-time size, horizon) before telemetry reveals them;
- (b) that text read into a small typed hypothesis set;
- (c) the reading's value measured in downstream inventory cost;
- (d) the damage from false or misleading text bounded by anytime-valid checks against telemetry.

Each ingredient exists on its own:
- Text that carries information: CiK, CAF-7M, Zhang et al.
- Supply-chain text reading: SHIELD, Foresight Learning, AlMahri et al.
- LLM reads and a solver decides: Ask-Clarify-Optimize, OptiGuide.
- Anytime-valid checks of LLM behaviour: E-valuator, CSA.
- False or distracting text: What If TSF, Corroboration Illusion, GSM-IC/DC.

**Sober caveats:**
- "Not found" is not "does not exist". Write "to our knowledge", scope the claim narrowly, and avoid "first".
- The anytime-valid mixture (certify-then-hedge) is the UV paper's contribution. In the follow-up it must be a tool, not a claim. The ACL-side contribution has to be about **language**:
  - what the alert text says and how well models read it;
  - which linguistic forms fail;
  - how calibrated the readings are;
  - when reading pays.
- The UV paper itself weakens the text-value story. On the UV alert bank, certify-then-hedge's development replays scored +107 to +158 on every model, including models that produced nothing usable, against +136 for the content-free variant (`paper/sections/08_results.tex`). In the UV setting the *alert timing*, not the *text*, carries most of the value. The follow-up is justified exactly because it builds a setting where text content matters. It must show that this setting is not contrived (see section 6).

**Closest competitors, and what each lacks compared with the follow-up:**

| Competitor | What it has | What it lacks here |
|---|---|---|
| UV 2026 paper (own) | Same method, same ladder, false alerts, content-free control | Alerts whose text states quantities; long-horizon warnings; NLP analysis. This is the main overlap risk. |
| CiK / Ashok et al. TMLR 2026 / CAF-7M | Text required for the forecast; execution gap; complementary contexts | Typed extraction, decision cost, verification, operational alerts |
| Foresight Learning (Turtel et al.) | Calibrated disruption probabilities from supply-chain news | Per-alert quantities, decisions, telemetry check |
| SHIELD (EMNLP Industry) | ACL-family supply-chain text reading | Quantities, decisions, verification |
| Ask, Clarify, Optimize | LLM reads and the solver decides, in inventory | Exogenous alerts; it argues information is *not* the bottleneck |
| NOTAM-Evolve / Knots | Short alerts to structured fields, with a benchmark | Decision and outcome link |
| What If TSF / Corroboration Illusion | Counterfactual or injected text susceptibility | Any mechanism that bounds the damage |
| E-valuator / CSA | e-processes on LLM agent streams | Text as a prior; external telemetry |

**Suggested contribution framing (distinct from UV):**
1. A benchmark of short operational alerts with graded, typed information content (none, family only, family plus quantities, long-horizon) and graded reliability, aligned with simulated outcomes and with a real-text validation subset.
2. Measurement of reading accuracy, error types and calibration per field (magnitude, onset, lead-time size, horizon) across the model ladder on that benchmark.
3. Field-level "value of reading": how much of the downstream cost each reading error causes.
4. Susceptibility to false alerts and distractors, and how much of it downstream verification absorbs.

---

## 4. Candidate real-text datasets with outcomes

Bottom line (datasets searcher, and consistent with my reading): **no public dataset pairs supplier lead-time or delay notices with measured lead times.** An informative-alert stratum that runs the full inventory loop therefore has to be synthetic or controlled. Real text can support a **reading-to-outcome validation** and **realism anchoring**, not the full decision loop.

| Dataset | Real text | Measured outcome | Access / licence | Informative-alert stratum? | Real-text validation? |
|---|---|---|---|---|---|
| openFDA Drug Shortages https://open.fda.gov/apis/drug/drugshortages/ | Free-text `shortage_reason`, `related_info`, `resolved_note` | Posting, change, resolution and discontinuation dates, so onset and duration | CC0 1.0 "unless otherwise noted"; daily; 1,599 records (API, 2026-09-28) | No: no inventory telemetry | **Best candidate.** Test whether reading the cause (supply or demand) and any stated expected timing predicts realised duration, with calibration. Caveat: text fields are sparse (in the first 1,000 records, `shortage_reason` 244, `resolved_note` 6, `change_date` 10). |
| ShortageSim https://ojs.aaai.org/index.php/AAAI/article/view/41172 | FDA shortage announcements (2,925 events) | Resolution status and lag | Code and data https://github.com/Lemutisme/ShortageSim (MIT) | Partly: a simulator exists, but the reading task is not typed | Good companion to openFDA. The 2023–2024 window, Internet Archive sourcing and cause categories are not verified. |
| LLM4Delay / ICNDelay https://huggingface.co/datasets/petchthwr/ICNDelay | Coded NOTAM, METAR and TAF text | Delay minutes | HF licence tag MIT; repo licence not detected | No: aviation, not inventory | **Yes, out of domain.** Reading short coded alerts into a quantity with a measured outcome. Scope (Incheon 2022) not verified. |
| IMF PortWatch https://portwatch.imf.org/datasets/d9b37bf4b2104c85aebdcc0c1d8a2ab7_0/about | Mostly structured GDACS red alerts plus geopolitical disruptions | Daily AIS port calls and tonnage (a telemetry analogue) | IMF terms plus GDACS terms; commercial reuse unclear | No: little text | Useful for "telemetry reveals late" (throughput drops), only if paired with separately sourced text. Pairing not provided. |
| Foresight Learning set https://huggingface.co/datasets/LightningRodLabs/supply-chain-predictions | News | Realised disruption shock (label definition not verified) | 452 examples; **no licence stated** | No | Calibration comparator only. Redistribution unclear. |
| CiK https://proceedings.mlr.press/v267/williams25a.html | Hand-written context on real series | Real series | Apache-2.0 | Protocol model (includes distractor tasks) | Not real alerts |
| Time-MMD (NeurIPS D&B 2024) | Government reports and web search results | Weekly or monthly series | Data licence unsure | No: not alert-level | Weak |
| From News to Forecast | GDELT and other news | Load, FX, bitcoin, traffic | Repo MIT | No | Weak (news fusion) |
| TimesX https://arxiv.org/abs/2607.06973 | Time-stamped events and more | 190 real variables | No release found | No | Cite its post-cutoff leakage protocol |
| LEAF https://arxiv.org/abs/2605.16358 | Retrieved, fact-checked event text | Commodities, load, temperatures | No licence file | No | Cite its publication-time checking protocol |
| Balashankar et al. https://doi.org/10.1126/sciadv.abm3449 | 11.2M news articles | Food-crisis phases up to 12 months ahead | Corpus not shared | No | Evidence for long-horizon warnings only |
| CrudeOilNews https://aclanthology.org/2022.lrec-1.49/ | Commodity news with shock events and arguments | None built in (would need joining to prices) | MIT, academic use only; article links, not full text | Annotation template | Weak |
| EDT, Lee et al. 2014 | Finance news, 8-K filings | Price reactions | No licence stated | No | Out of domain |

**Recommendation:**
- Use openFDA/ShortageSim as the in-domain real-text validation (reading to realised duration, plus calibration), and ICNDelay as an out-of-domain check on reading short coded alerts.
- Use real notices (FDA shortage text, NOTAM style) as style exemplars for synthetic alerts, and have raters judge realism (synthetic versus real).
- Do not claim real-world inventory validation. None of these datasets supports it.

---

## 5. Design implications for an informative-alert study

Repo observations that motivate the design:
- In the UV pilot, magnitude matched in only 8 of 96 and 7 of 96 episodes, because every non-distractor template says `medium` while the truth is `low` in 80 of 96 (`analysis/real_content_pilot/REPORT.md`, `collie/data/alerts/templates/dev.yaml`). Magnitude in the current bank is neither informative nor aligned with the truth.
- The UV gains sit almost entirely on lead-time shifts, and lead times are deterministic (`paper/sections/11_limitations.tex`).
- The bank yields distinct texts for only eight units per family.
- The content-free control removes the text but not the alert channel.

**What alerts should state.** Generate the shock first, then render the text, so labels are exact by construction. Cover every ShockSpec field (`target_stream`, `shock_family`, `direction`, `onset_window`, `magnitude_bin`, `persistence`, `duration_bin`, per `collie/contracts.py`) and cross it with:
- **Information level:**
  - L0: content-free ping.
  - L1: family and direction only (the UV-like level).
  - L2: plus magnitude.
  - L3: plus onset and duration.
  - L4: plus a lead-time size, e.g. "lead times move from about 2 to 5 weeks".

  This gives a text-ablation ladder that assigns value to each field, and it fixes the UV control's confound.
- **How quantities are expressed:**
  - exact numerals ("+40%");
  - relative forms ("roughly doubled");
  - vague quantifiers ("markedly", "slightly");
  - ranges;
  - unit changes (days versus weeks versus periods);
  - absolute dates versus relative offsets;
  - negation and hedging.

  This is what makes the reading an NLP problem. Without it a regex solves L2–L4.
- **Complementarity** (CAF-7M, Zhang et al.): for each episode, compute a *telemetry reveal time*, the first period at which a telemetry-only detector (e.g. the UV CUSUM or HMM controls) identifies the family and magnitude at a fixed error level. Then vary the alert's lead over that time.
  - Report the value of text as a function of that lead and of the shock's magnitude.
  - Make lead times noisy (stage D already registers noisy lead times; commits `fae3714`/`fa59cf4`), so that telemetry is genuinely slow.

**Long-horizon warnings.**
- Alerts announce onsets k periods ahead ("from next quarter"), with k both shorter and longer than the lead time. Before onset, no e-process evidence can accumulate, so the text-derived prior alone drives pre-positioning. This is where text is uniquely valuable and where false warnings cost the most.
- Include warnings that never materialise, postponed onsets, and follow-up messages ("update: delay resolved", "revised to 3 weeks"). Evaluate reading of multi-message threads, not just single alerts.
- Check that the onset-window registry admits future onsets. The UV bank uses windows near ±1 period.

**Distractors and false alerts.** Cross the information levels with reliability: accurate, overstated, understated, mis-timed, stale, wrong entity (another SKU or supplier), counterfactual (What If TSF), and injected or fabricated (Corroboration Illusion). Add GSM-IC/DC-style irrelevant numerals (order numbers, prices, dates) to test anchoring. Keep null twins with false alerts. Hold out wording families and templates, and add human-written paraphrases, to test generalisation beyond templates.

**Reading-accuracy evaluation:**
- Accuracy per field.
- Ordinal error for binned fields (over versus under).
- Absolute error for stated numbers and onset.
- Unit and temporal-resolution errors.
- **Hallucinated fields when the text is silent.** The correct answer is null or abstain. Report selective accuracy against abstention rate.
- An error taxonomy: stream confusion (demand versus supply), direction flips, magnitude misbinning, unit errors, timing errors, distractor uptake, and wrong-entity uptake.
- **Decision-weighted error:** replace one field with the truth, recompile, and measure the change in cost. This ties NLP errors to consequences and is the main bridge between NLP and OR.
- Across the ladder: reading accuracy against net reward, and whether reading accuracy predicts decision value. The UV ladder found, post hoc, that the loss from acting at once grew with how readily a model commits and that, since commitment and accuracy moved together, being right did not protect a model; this must be re-tested, not re-reported.
- Control multiplicity for model comparisons (Holm, or anytime-valid e-Holm as in BB-EDGE).
- Human baseline: two annotators per sampled alert. Agreement sets a ceiling and flags truly ambiguous alerts.

**Calibration:**
- Elicit a distribution over bins per field, either as verbalized probabilities or as frequencies over K samples.
- Score Brier score, log loss and ECE per field against generator truth, and on openFDA against realised outcomes.
- If the mixture's prior weight on the named hypothesis is set from the model's stated confidence, calibration directly sets exposure. Test fixed versus confidence-set weights as a registered secondary analysis. This makes calibration matter for decisions, not just as a descriptive metric.
- Gligorić et al. show how a few human labels can correct LLM annotation bias. Use it for the real-text subset.

**Baselines reviewers will expect:**
- a rule/regex extractor;
- a small fine-tuned extractor;
- direct context-aided LLM forecasting (CiK-style) feeding the compiler;
- LLM Processes-style text-to-prior;
- end-to-end LLM ordering;
- telemetry-only;
- a perfect-reading oracle, which UV already has.

**Leakage:** synthetic text avoids memorisation. For real text, use post-cutoff windows (TimesX) and checked publication times (LEAF).

**What makes the result an NLP contribution rather than an OR paper with an LLM parser:**
1. A released dataset and benchmark of alerts with typed quantitative labels, information levels, reliability classes, human realism ratings and a real-text subset.
2. Linguistic findings: which forms of expression (vague quantifiers, relative versus absolute time, units, hedges, retractions, distractor numerals) cause which field errors, and how this scales across 21 models.
3. Calibration of quantitative extraction.
4. A value-of-reading metric that links field errors to cost.
5. Robustness to false text, with evidence of how much downstream verification absorbs.

The need for citations on hedging, vagueness and temporal expressions was not covered by these searches. That is a gap to fill.

---

## 6. Risks: what an ACL reviewer would object to

1. **"This is the UV paper again."** The ladder, false alerts, content-free control and the method all appear in UV. ARR allows "no overlap in stated contributions", up to 10% text reuse (the IEEE paper is not exempt), and desk rejection for self-plagiarism. Mitigation:
   - new data (the informative bank);
   - new research questions;
   - no restated UV results;
   - an explicit third-person difference statement and disclosure.
2. **"Not NLP."** The schema is a handful of bins, which looks like slot filling, and the statistics are the real contribution. Mitigation: the linguistic variation, error taxonomy, calibration and benchmark release in section 5. Show that a regex baseline fails on the varied phrasings.
3. **"You built the setting so text wins."** The informative stratum is constructed, and UV's own replays showed the text adding little over a content-free prior. Mitigation:
   - pre-register the strata;
   - report uninformative and misleading strata with equal weight;
   - quantify complementarity (telemetry reveal time; CAF-7M's argument);
   - use the openFDA/ICNDelay validation to show that real notices do state such quantities sometimes, with prevalence reported honestly.
4. **Synthetic, template-written alerts.** Template artifacts may leak labels. Mitigation: held-out wording families, human paraphrases, realism ratings, and a real-text subset.
5. **External validity of the simulator.** It is one generator, and UV has deterministic lead times and no InventoryBench run (UV limitations). Theorem premises do not hold exactly (plug-in null, exposure 2–3.7× bounds in UV's Monte Carlo). Expect questions about whether guarantees quoted from UV apply.
6. **Why e-processes?** Schirmer et al. show that simple calibrated thresholds detect failures as well or earlier. A reviewer can ask for a conformal-risk-control or threshold baseline for the verification step.
7. **Statistics across 21 models.** Multiple comparisons, few seeds per cell, and closed API models that may be deprecated (reproducibility). Specify multiplicity control and release prompts and outputs.
8. **Calibration elicitation.** Verbalized confidence is known to be unreliable, and results may depend on the elicitation method. Report at least two methods.
9. **Missing ACL baselines and citations.** CiK, Ashok et al. (execution gap), What If TSF, Corroboration Illusion, SHIELD, SupChain-Bench, the Campos et al. survey. Many key comparators are 2026 preprints (unrefereed; some posted in the last month), so their standing may change before review.
10. **Data licences.** The Foresight set, LEAF, EDT and Time-MMD lack clear licences, and PortWatch commercial reuse is unclear. Prefer CC0 openFDA and MIT-tagged ICNDelay for anything released.
11. **Venue logistics.**
    - AACL 2026 is closed and AACL 2027 is unannounced.
    - The October 12 ARR cycle collides with the UV camera-ready (October 15).
    - The new sustainable-reviewing policy needs a named service contributor and ORCID profiles.
    - The preprint declaration is affected by the published, non-anonymous UV paper.