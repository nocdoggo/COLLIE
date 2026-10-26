# Plan B research brief

This brief gives the people revising the Plan B slides, poster and documentation checked outside sources on competitors, community need and responsible use of AI, with what each source supports and what it does not.

Written October 26, 2026. The audit of the same day (`AUDIT_BEFORE.md`, fixes 2 and 3) found that competitors and sources are missing from the slides and the poster and thin in the documentation. Every outside fact below comes from a finding that was checked against its source page before this brief was written. Cite each source by its number in the reference list. Each tool is described only by what its own page says. We have not tested any of these tools.

## Direct competitors

These are event platforms and AI assistants that already change schedules or plans, often after a person approves.

| Tool | What its own page says it does | What Plan B does differently | Source |
| --- | --- | --- | --- |
| Sessionboard AI Agenda Builder | When a speaker cancels, a session moves or a room becomes unavailable, its AI assesses the impact on the rest of the agenda and surfaces the most viable adjustments. Its assistant reviews every change against the agenda's rules, and speaker availability is checked automatically when a session is scheduled. Audit and approval flows send significant changes through sign-off before they go live. | This is the closest competitor to the projector and volunteer story, so impact assessment, rule checks and approval before publishing are not new. The page does not describe expiring backup holds or a written receipt for each decision, and Plan B can show both. | [1] |
| Cvent Assistant for attendee management (announced) | A press release of July 14, 2026 says organizers can paste an attendee change request, and the Assistant maps every required change across the platform, such as registration updates, session swaps, hotel changes and package adjustments. It then presents them for one-click review and execution. The feature is expected in Q3 2026. | Plan B checks the one fact that could change the decision, frees holds when they expire and writes a receipt for every accepted change. The release mentions none of these. Call the Cvent feature announced in July 2026 and expected in Q3 2026, and do not say whether it has shipped. | [2] |
| Bizzabo Agentic Operating System for Events (announced) | Announced October 12, 2026. Its agents include a Content Manager that builds and updates event schedules from a prompt, and a Setup Reviewer that runs a pre-launch health check that catches errors before attendees see them. Nothing the agents change goes live until a person approves it. Existing customers get early access this fall, and the full system is planned to be broadly available in early 2027. | Approval by a person before changes go live is expected practice here, so it is not a difference. The announcement does not describe a targeted fact check before a change on the day, or an expiring backup hold, and Plan B can show both. | [3] |
| ChatGPT agent (OpenAI) | It can automate tasks such as rearranging meetings and planning and booking offsites, and it can design and book entire dinner parties. ChatGPT is trained to ask for the user's permission before actions with real-world consequences, such as making a purchase. | Asking before spending is not new. In Plan B the model picks only among options that the server built and checked for one event. | [4] |
| Browse with Copilot (Microsoft) | Copilot performs actions in the Edge browser, such as clicking, typing and navigating tabs. It asks for the user's attention and supervision for certain actions, such as buying an item or booking a reservation. | The approval itself is common. What Plan B adds around the approval is the event-specific check, the hold and the receipt. | [5] |
| Gemini Apps tasks (Google) | Once Google Workspace is connected, Gemini can check a calendar, schedule new events, update meeting times, change locations or cancel events. It is designed to always ask for review and confirmation before certain actions, such as making purchases or sending communications. | Calendar editing is not Plan B's value. Plan B checks whether a warning is true before it changes a shared event plan. | [6] |
| Zapier Agents | A user can make an agent stop and wait for confirmation by adding a sentence asking for it to the agent's instructions, or by adding a Human in the Loop step after the agent step in a Zap. The page says Zapier is moving Agents to AI by Zapier, so the product name may change. | In Zapier the user sets up the approval step. In Plan B the server's rules decide which changes are allowed, and spending always needs a person. | [7] |
| Eventbrite AI tools (2023 blog post) | From an event title, location and dates, the tools suggest an event summary and description, and even an AI-generated image. They also write copy for event pages, emails and social media ads. | These tools create and promote an event. The post says nothing about changes on the day, checking facts or approving spending, which is where Plan B works. The post is from 2023, so Eventbrite's current features may differ. | [8] |
| Whova AI features | An AI Companion helps organizers improve event descriptions. An AI-Generated Event Summary produces a report after the event with basic event details and metrics such as attendance numbers and session counts. The same guide tells organizers to check the facts, because AI can make up information. | These features are about writing and reporting, not about a last-minute problem, so they do not overlap directly with Plan B. The guide's advice to check the facts supports Plan B's choice to check a fact before acting. | [9] |
| Reclaim.ai | Users can talk to its AI scheduling assistant to resolve conflicts or adjust meetings, with preview and approval controls before changes are applied. It adapts meetings, tasks and focus time as a schedule changes during the week. | This is an adjacent tool for personal and team calendars, not for community events with shared equipment and volunteers. Preview and approval before rescheduling is common, so stress the fact check, the backup hold and the receipt. The page ties preview and approval to changes the user asks for in conversation, not to every automatic change. | [10] |

OpenAI's page refuses automated readers, so its text was checked against the Internet Archive copy saved on October 10, 2026, which is listed with reference 4.

The free backup hold is a difference only some cases can show. Jordan's projector story has no hold, and the hold appears in a separate development case (`AUDIT_BEFORE.md`, section 9). Label it that way wherever the hold is used as a difference.

A line the slides and the poster can use. Event platforms already check agenda changes against rules and send big changes for sign-off [1], and two have announced agents that turn a request into changes a person reviews or approves before they take effect [2, 3]. General assistants already ask before they buy or book [4, 5, 6]. Plan B shows three things on one community event. It checks the one fact that could change the decision, lets the AI pick only among options the server built and checked, and writes a receipt for every accepted change while any spending waits for a person. We have not tested the other tools.

## Indirect competitors and the status quo

These are the tools where a late message lands today, or where an event is set up before the day.

| Tool | What its own page says it does | What Plan B does differently | Source |
| --- | --- | --- | --- |
| GroupMe (Microsoft) | A free group messaging app. Its GroupMe Campus tab is for finding groups for classes, clubs and common interests in your school community, which requires verifying a school email address. | A group chat is where a late warning such as a delayed projector usually lands. The page describes messaging, announcement groups and finding groups. It does not describe checking a fact, holding a backup or recording a plan change. Plan B works behind the chat and does not replace it. | [11] |
| Google Sheets | Google's page, titled Collaborative, AI-powered spreadsheets, says people can view, edit and collaborate from a phone, tablet or desktop, that permissions control who can view, comment or edit, and that Gemini can handle the calculation once you define your goals and constraints. | Sheets stands in for the shared run-of-show or volunteer spreadsheet. A spreadsheet already offers AI help with goals and constraints, so the pitch should rest on what Plan B adds, which is server-checked rules, expiring holds and a receipt for each accepted change. It should not rest on the fact that Plan B uses AI. | [12] |
| Doodle group polls | Group polls let you send people a set of times and see which one works best for your event. You can turn on automatic reminders or set a deadline. | Polls settle when to meet before the event. Plan B handles what happens after the time is set, when a message on the day threatens a commitment, so it complements polls rather than competing with them. | [13] |
| CampusGroups (Ready Education) | A student engagement platform with tools for student organizations, clubs and campus departments to organize events, manage memberships, communicate with members and track attendance. | It covers events, membership, messaging and attendance. Plan B decides what to do when a last-minute update arrives, so the slide can say Plan B sits alongside platforms like this. | [14] |
| UMBeInvolved (UMass Boston) | All UMass Boston students have access to UMBeInvolved, the portal for all student groups active through the Office of Student Activities and the student governing bodies, where students can search for a club or current events. Its link for online registration of new organizations points to a umb.campusgroups.com address. | This grounds the local status quo for the campus showcase. UMass Boston student groups already use a portal hosted on CampusGroups. It implies no integration, data access or endorsement for Plan B. | [15] |
| Engage from Encoura (formerly Anthology Engage) | The old Anthology Engage address on anthology.com now redirects, by way of blackboard.com, to an Encoura page that calls Engage the co-curricular platform for student affairs, with event planning, digital event reviewer workflows, room and resource integration and advanced RSVP functionality. Encoura's page at encoura.org/anthology says Encoura acquired Anthology's Lifecycle Engagement and Student Success solutions as of February 2, 2026. | Its event reviewer workflows belong to planning an event ahead of time, which is a different job from Plan B's recovery on the day. Name the product Engage from Encoura, formerly Anthology Engage. | [16] |
| SignUpGenius | Organizers create a sign up for volunteers, events or schedules. Automatic reminders help people show up, and automatic waitlists fill open slots the moment a participant cancels and notify waitlisted participants. | This is the closest status quo answer to a volunteer dropping out. The page describes filling a cancelled slot and sending reminders. It does not describe checking how a late arrival affects the activities that depend on it, which is the gap Plan B targets. | [17] |
| VolunteerHub | Its scheduling feature lets volunteers self-manage their shifts. Its FAQ says nonprofits use volunteer management software instead of relying on spreadsheets, email or manual processes. | This is a vendor's own account of the status quo, which it describes as spreadsheets, email and manual processes. Cite it as vendor framing, not as independent evidence of how organizers work. | [18] |
| PantrySoft | Students can register for a campus pantry online, the portal schedules student appointments with automated reminders by text or email, and the pantry can track visits and flag missed appointments for follow-up. | This is context for the Pantry Continuity showcase. The UMass Boston U-ACCESS food pantry page tells students to register for U-ACCESS Pantry Soft and links to a PantrySoft login [29]. Describe Plan B as handling a distribution day's last-minute changes next to an intake tool like this, with no claimed integration. | [19] |
| Link2Feed | Its food bank and pantry page, describing the problems its software is built to solve, says these programs depend on volunteers to keep services running, and that keeping paper records up to date and getting a de-duplicated client count can feel impossible. | Use it, as vendor framing, for a modest statement that pantries rely on volunteers and that paper records remain a pain point. Its duplicates problem is about client records. Plan B's handling of a repeated warning message is a different thing, so do not conflate the two. | [20] |

A line the slides and the poster can use. Today a late message lands in a group chat, a shared spreadsheet or a sign-up sheet [11, 12, 17]. Plan B works behind these tools and does not replace them.

## Target market and community need

Plan B is meant for student organizers, clubs, volunteers and pantry staff who run small community events (the documentation's abstract). The facts below size the people and the need around those events. None of them measures demand for Plan B.

| Fact | Data period | Published | Source | Use it for, and its limit |
| --- | --- | --- | --- | --- |
| An estimated 23 percent of US college students, about 3.8 million, experienced food insecurity. Fewer than two in five food insecure students were potentially eligible for SNAP, and 59 percent of those did not report receiving SNAP benefits. | 2020 | GAO-24-107074, published June 24, 2024, publicly released July 24, 2024 | [21] | The federal estimate of college food insecurity, for the problem slide, the poster need panel and the product brief. Give the data year 2020 and the report year 2024. It shows that campus food support is needed. It does not show demand for Plan B. |
| More than 650 colleges reported having a food pantry on campus that provides free food to college students in need. | As of September 2018 | GAO-19-95, published December 21, 2018, publicly released January 9, 2019 | [22] | A size for the campus pantry segment that the Pantry Continuity showcase speaks to. Present it as a 2018 count that colleges reported, not as a current total. |
| Among 74,350 survey participants at 91 institutions in 16 states, 59 percent had at least one form of basic needs insecurity related to food or housing, and 41 percent had food insecurity. | Spring 2023 to Summer 2024 | The Hope Center, February 2025 | [23] | A newer measure of student need to pair with the GAO estimate. It covers students at institutions that chose to take part and field the survey, so it is not a national rate and should not be compared directly with GAO's. |
| Over 75.7 million people, or 28.3 percent of the US population age 16 and up, formally volunteered through an organization. | September 2022 to September 2023 | U.S. Census Bureau with AmeriCorps, November 19, 2024 | [24] | How many people do the volunteer and facilitator work that community events depend on, which matches the volunteer roles in the Plan B scenarios. It counts volunteers, not events or organizers. |
| Formal volunteers served an estimated 4.99 billion hours and contributed over $167.2 billion in economic value. The same source names food banks as an example of an organization people formally volunteer through. | September 2022 to 2023, from survey data collected in September 2023 | U.S. Census Bureau, November 19, 2024 | [24] | Volunteer time is a large and valuable resource that an event plan should not waste on unneeded changes. Attribute the dollar value to AmeriCorps' analysis. It does not measure how much time last-minute changes cost. |
| Nearly 48 million people in the US, including 14 million children, experienced food insecurity, according to USDA. About 25 million people, nearly half of all people experiencing food insecurity, had incomes too high to qualify for federal nutrition assistance, according to Feeding America's Map the Meal Gap study. | 2024 | Feeding America press release, July 28, 2026 | [25] | National context for why pantries and their distribution days matter beyond campus. Attribute 48 million to USDA as reported by Feeding America, and 25 million to Map the Meal Gap. Use the source's phrase "nearly half of all people experiencing food insecurity" rather than an exact share of the 48 million. |
| A record 40 percent of Massachusetts households, about 1.1 million, experienced food insecurity, and 56 percent of food insecure households depended on the charitable food system. Over 600 community-based pantries and other local partners in 190 cities and towns depend on The Greater Boston Food Bank. | 2025 | The Greater Boston Food Bank and Mass General Brigham, April 7, 2026 | [26] | Local Boston context for a pantry showcase built at UMass Boston, and a count of the community pantries in one regional network. It comes from an online survey of more than 3,000 Massachusetts adults run from October to December 2025, with its own method, so do not compare its 40 percent with USDA national rates. |
| About 19.0 million students attended colleges and universities, including non-degree-granting institutions. | Fall 2022 | National Center for Education Statistics | [27] | The outer size of the campus population whose clubs, showcases and events the campus profile targets. It counts students, not student organizations or event organizers, so it is not a market size for Plan B. |
| UMass Boston invites students to join one of its 100+ student groups and organizations. | Page checked October 26, 2026 | UMass Boston | [28] | A concrete local count of the student groups that could organize events at the host campus. It is not evidence that any group wants or would use Plan B. |
| The U-ACCESS food pantry opened in February 2013, relies on the UMass Boston community to support its operations, and is a founding member of the College and University Food Bank Association. | Opened February 2013 | UMass Boston U-ACCESS | [29] | Grounds the pantry showcase in a real campus pantry that depends on community support. Do not imply a partnership, an endorsement or access to its data, since the showcase uses a fictional pantry and synthetic stock. |

A line the slides and the poster can use. Community events run on volunteers, and over 75.7 million people in the US volunteered through an organization between September 2022 and September 2023 [24]. On campus, GAO estimated that 23 percent of college students experienced food insecurity in 2020 [21], and more than 650 colleges reported a campus food pantry in 2018 [22].

## Responsible use of AI

Plan B's five practices are below, each with what the sources say and how Plan B meets it. Every run in Plan B's model spend summary that reports a model reports Claude Sonnet 5.5 from Anthropic, so [36] is the model vendor's own guidance. That page is written for a different tool, so cite it as related vendor guidance, not as a rule written for Plan B.

### 1. Check before acting

**What the sources say.** OWASP's 2025 Top 10 for LLM applications lists prompt injection as LLM01. It says indirect prompt injection happens when an LLM accepts input from outside sources such as websites or files, and among measures that can reduce the impact it lists separating and clearly marking untrusted content [33]. OWASP's Excessive Agency entry (LLM06) recommends putting authorization in downstream systems rather than relying on an LLM to decide whether an action is allowed [34]. The UK National Cyber Security Centre says current LLMs do not enforce a security boundary between instructions and data inside a prompt, and that protections should focus more on deterministic, non-LLM safeguards that constrain what the system can do [37]. Anthropic warns that in some circumstances Claude follows commands found in content even when they conflict with the user's instructions [36]. Whova's guide also tells organizers to check the facts, because AI can make up information [9].

**How Plan B meets it.** A message from a volunteer or a vendor is a claim, not a fact, and its text is treated as data, not as instructions. Plan B checks only the one fact that could change the decision, such as one status check on the delayed projector. The server builds the possible fixes from fixed templates and checks each against the deadline, the people and the budget. The AI picks only among the options that passed, and the server's rules, not the model, decide whether a change is accepted. A misleading or injected message can at most lead to a choice among options the server has already checked.

**Careful.** OWASP presents these as measures that reduce impact, and the NCSC warns against any claim to stop prompt injection. Say that Plan B limits what a misleading message can do. Do not say that it prevents prompt injection.

### 2. A person approves spending

**What the sources say.** OWASP lists requiring human approval for high-risk actions among the measures that reduce the impact of prompt injection [33], and its Excessive Agency entry recommends a human in the loop who approves high-impact actions before they are taken [34]. The OpenAI paper by Shavit and colleagues says some decisions may be too important to delegate to agents, such as independently starting an irreversible large financial transaction. It calls requiring a user to authorize such actions a standard way to limit egregious failures, and notes that having to approve many decisions quickly reduces a person's ability to consider each one (section 4.2) [35]. Anthropic lists asking a human to confirm decisions with meaningful real-world consequences, such as completing financial transactions, among the precautions to consider [36]. NIST AI RMF 1.0 says, in a list of issues that merit further research, that human roles and responsibilities in decision making and in overseeing AI systems need to be clearly defined and differentiated (Appendix C, page 40) [32].

**How Plan B meets it.** Each role has a written list of the actions it may take, and the server enforces that list. The AI coordinator's standing permission covers small sandbox actions. It may check a fact, place a free hold that expires on its own, or apply a change the server's rules allow. Any spending waits for the organizer, who approves it in their own session, and no participant gains spending authority from a message. The organizer is asked only about actions beyond the standing permission, which answers the concern about many quick approvals.

**Careful.** Approval before spending is common practice among the direct competitors, so present it as responsible design, not as something new. The OpenAI paper does not propose standing permissions, so present the standing permission as Plan B's own design choice that the paper's concern motivates. The NIST passage sits in a list of open issues, so cite it as framing, not as a NIST requirement.

### 3. A receipt for every change

**What the sources say.** NIST AI RMF 1.0 lists accountable and transparent among the characteristics of trustworthy AI. It says this characteristic covers, among other things, how and when deployment, post-deployment or end user decisions were made and by whom, and that transparency is often needed for actionable redress when outputs are incorrect (section 3.4, page 15) [32]. The OpenAI paper says it may be particularly important to give the user a ledger of actions taken by the agent, and that actions which can only be reviewed after the fact should be more easily reversible than those that require approval (section 4.4) [35].

**How Plan B meets it.** The server writes a receipt for every accepted change, and the AI cannot write one. Refused requests are recorded too, some as attempts without a receipt. The receipts act as the ledger of actions the OpenAI paper describes, so an organizer can see what changed and trace a wrong change in order to correct it. A free hold expires on its own, so it is the kind of reversible step that can be reviewed after the fact without asking first.

**Careful.** Neither source requires this exact design. Say that the receipt follows these ideas, not that NIST or OpenAI calls for it.

### 4. A sandbox

**What the sources say.** τ-bench evaluates agents by comparing the database state at the end of a conversation with the annotated goal state [30]. The same paper also proposes a metric, pass^k, for how reliably an agent behaves over multiple trials [30]. NIST's AI Risk Management Framework is intended for voluntary use, to help bring trustworthiness considerations into the design, development, use and evaluation of AI systems [31]. Its list of the characteristics of trustworthy AI includes valid and reliable, safe, and secure and resilient [32].

**How Plan B meets it.** Everything runs in a fictional local sandbox. Every action is a change to a local database and nothing else, and no university booking, purchase, delivery or message is made. Held-out cases are scored by the final state of the sandbox, not by how good an explanation sounds. The approaches that use the model run each held-out case three times as repeated trials. Paid model calls run only under spending caps for each run and in total.

**Careful.** Plan B counts the runs that met the expected outcome and does not compute pass^k. Cite τ-bench for scoring by end state and, in a separate sentence, for the idea of repeated trials. Keep the paper's official title, and do not present its 2024 results as current agent performance. Say that Plan B's design draws on the NIST framework's trustworthiness ideas, not that it complies with the framework or is certified against it. NIST says AI RMF 1.0 is being revised, so cite it as version 1.0 of January 2023.

### 5. No personal data

**What the sources say.** NIST AI RMF 1.0 lists privacy-enhanced among the characteristics of trustworthy AI [32].

**How Plan B meets it.** All events, people, rooms, stock, timings and costs are fictional. The pantry plans aggregate kit counts only, with no recipient identities and no eligibility, allergen or medical decisions. No participant feedback was collected and no real message was sent. The pantry showcase is inspired by the public context of campus food services, and no pantry, U-ACCESS staff, system or partner took part.

**Careful.** The sources state principles and did not review Plan B. Say that the sandbox uses no personal data, not that Plan B meets a privacy standard.

## Key sources and acknowledgement

### How to cite

Cite by number in square brackets, for example [21]. The documentation carries the full list below. The owner's writing rules for the deliverables allow no colon and no https in visible text (`AUDIT_BEFORE.md`, section 1), so print each address there without its https prefix, for example www.gao.gov/products/gao-24-107074. Titles are given as each page prints them, with the site name moved after the title and a dash inside a title written as a comma. Some official titles contain a colon, which belongs to the title. On a slide or the poster, that colon can become a comma.

### References

Direct competitors

1. AI Agenda Builder & Event Scheduler (2026). Sessionboard. https://www.sessionboard.com/capabilities/ai-agenda
2. Cvent Unveils More Than 70 Product Innovations at Cvent CONNECT 2026, Backed by $1 Billion Technology Investment. Cvent press release, July 14, 2026. https://www.cvent.com/en/press-release/cvent-unveils-more-70-product-innovations-cvent-connect-2026-backed-1-billion
3. Bizzabo Reveals Its Agentic Operating System for Events. Bizzabo, October 12, 2026. https://www.bizzabo.com/blog/bizzabo-reveals-its-agentic-operating-system-for-events
4. Introducing ChatGPT agent. OpenAI. https://openai.com/index/introducing-chatgpt-agent/ The text was checked against the Internet Archive copy saved on October 10, 2026, at https://web.archive.org/web/20261010075929/https://openai.com/index/introducing-chatgpt-agent/
5. Browse with Copilot. Microsoft Support. https://support.microsoft.com/en-US/microsoft-copilot/browse-with-copilot
6. Manage your tasks & workflows in Gemini Apps. Gemini Apps Help, Google. https://support.google.com/gemini/answer/16596215
7. Add approval steps to your agent's instructions. Zapier Help Center. https://help.zapier.com/hc/en-us/articles/41776074420493
8. Eventbrite Reimagines Events With the Debut of AI-Powered Tools. Eventbrite blog, May 9, 2023. https://www.eventbrite.com/blog/eventbrite-ai-powered-tools/
9. How to Use AI for Event Planning in 2026 with Real Examples. Whova blog, last updated August 20, 2026. https://whova.com/blog/ai-event-planning/
10. Reclaim, AI Calendar for Work & Life. Reclaim.ai home page. https://reclaim.ai/

Indirect competitors and the status quo

11. What is GroupMe? Microsoft Support. https://support.microsoft.com/en-us/groupme/what-is-groupme
12. Collaborative, AI-powered spreadsheets. Google Workspace. https://workspace.google.com/products/sheets/
13. Create a free group poll. Doodle. https://doodle.com/en/product/polls/
14. What is CampusGroups? Ready Education Help Center. https://helpcenter.readyeducation.com/what-is-campusgroups
15. Student Activities. UMass Boston. https://www.umb.edu/campus-life/clubs-activities/student-activities/
16. Engage, Student Engagement Platform from Encoura. Encoura. https://www.encoura.org/student-success/engage/ The old Anthology Engage address redirects here, and Encoura's note on the acquisition is at encoura.org/anthology.
17. Online Sign Up Sheets. SignUpGenius. https://www.signupgenius.com/sign-ups
18. Volunteer Management Software for Nonprofits. VolunteerHub. https://volunteerhub.com/platform
19. Campus Pantry Software for Colleges and Universities. PantrySoft. https://pantrysoft.com/customer/colleges-and-universities/
20. Food Bank & Pantry Software Solutions. Link2Feed. https://www.link2feed.com/food-banks-pantries/

Target market and community need

21. Supplemental Nutrition Assistance Program: Estimated Eligibility and Receipt among Food Insecure College Students. GAO-24-107074, U.S. Government Accountability Office, published June 24, 2024, publicly released July 24, 2024. https://www.gao.gov/products/gao-24-107074
22. Food Insecurity: Better Information Could Help Eligible College Students Access Federal Food Assistance Benefits. GAO-19-95, U.S. Government Accountability Office, published December 21, 2018, publicly released January 9, 2019. https://www.gao.gov/products/gao-19-95
23. 2023-2024 Student Basic Needs Survey Report. The Hope Center for Student Basic Needs, February 2025. https://hope.temple.edu/research/hope-center-basic-needs-survey/2023-2024-student-basic-needs-survey-report
24. New U.S. Census Bureau and AmeriCorps Research Tracks Virtual Volunteering for First Time. U.S. Census Bureau, November 19, 2024. https://www.census.gov/library/stories/2024/11/civic-engagement-and-volunteerism.html
25. Food insecurity reaches every U.S. community, with rural and southern counties facing the highest rates. Feeding America press release on Map the Meal Gap 2026, July 28, 2026. https://www.feedingamerica.org/about-us/press-room/Map-the-Meal-Gap-2026
26. Food Insecurity Rose to 40% in 2025, According to The Greater Boston Food Bank and Mass General Brigham's Sixth Annual Statewide Food Access Report. The Greater Boston Food Bank press release, April 7, 2026. https://www.gbfb.org/news/press-releases/hunger-on-the-rise/
27. Fast Facts: Back-to-school statistics (372). National Center for Education Statistics. https://nces.ed.gov/fastfacts/display.asp?id=372
28. Student Groups & Activities. UMass Boston, checked October 26, 2026. https://www.umb.edu/campus-life/clubs-activities/
29. Food Pantry. UMass Boston U-ACCESS. https://www.umb.edu/campus-life/current-students/u-access/food-pantry/

Responsible use of AI

30. τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains. Shunyu Yao, Noah Shinn, Pedram Razavi and Karthik Narasimhan, arXiv 2406.12045, submitted June 17, 2024. https://arxiv.org/abs/2406.12045
31. AI Risk Management Framework. NIST. https://www.nist.gov/itl/ai-risk-management-framework
32. Artificial Intelligence Risk Management Framework (AI RMF 1.0), NIST AI 100-1. NIST, January 2023. Section 3.4 on page 15 and Appendix C on page 40. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
33. LLM01:2025 Prompt Injection. OWASP Gen AI Security Project. https://genai.owasp.org/llmrisk/llm01-prompt-injection/
34. LLM06:2025 Excessive Agency. OWASP Gen AI Security Project. https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
35. Practices for Governing Agentic AI Systems. Yonadav Shavit and colleagues, OpenAI. Sections 4.2 and 4.4. https://cdn.openai.com/papers/practices-for-governing-agentic-ai-systems.pdf
36. Computer use tool. Claude Platform Docs, Anthropic. https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
37. Prompt injection is not SQL injection (it may be worse). Dave Chismon, National Cyber Security Centre blog, December 8, 2025. https://www.ncsc.gov.uk/blog-post/prompt-injection-is-not-sql-injection

### Suggested thanks

For the documentation. Thanks to the Paul English Applied AI Institute (PEAAII) at UMass Boston for organizing the hackathon. Plan B's AI coordinator runs on Claude Sonnet 5.5, a model made by Anthropic, reached through OpenRouter. The slides use the elegant beamer theme by Lars Spreng (CC BY 4.0), and the poster uses the Gemini beamerposter theme by Anish Athalye (MIT License) with the UMass Boston colour theme from the Overleaf poster template. The app's server uses the open-source libraries FastAPI, uvicorn and Pydantic. Thanks do not imply that any of them endorses Plan B.

For the slide and the poster. Thanks to the PEAAII organizers at UMass Boston, to Anthropic for the Claude model and OpenRouter for access to it, and to the authors of the elegant and Gemini templates. Sources 1 to 37 are listed in the documentation.

Where these facts are recorded. The model and its provider are in `handoffs/wave_2/DECISIONS.md` (W2-D1), and every run that reports a model in the Wave 2 model spend summary reports this same model. The template authors and licenses are in this folder's `README.md` under Template credits. Print the model's name, not its code string, on the slides and the poster.

## What not to claim

1. Do not say a competitor lacks a feature unless its own page says so. Say that its page does not describe the feature, and say that we have not tested the other tools.
2. Do not present approval before spending or before publishing as new. Sessionboard, Bizzabo, OpenAI, Microsoft, Google, Zapier and Reclaim all describe a person approving or confirming changes [1, 3 to 7, 10]. Do not present impact assessment or rule checks as new either, since Sessionboard describes both [1].
3. Do not say that Cvent's or Bizzabo's agents have shipped. Cvent's feature was announced in July 2026 and expected in Q3 2026 [2]. Bizzabo's early access starts this fall, and broad availability is planned for early 2027 [3].
4. Do not describe Eventbrite's current features from its 2023 post [8].
5. Do not claim any integration, partnership, endorsement or data access with UMass Boston, UMBeInvolved, CampusGroups, U-ACCESS, PantrySoft or any other named product or service. The pantry is fictional and its stock is synthetic.
6. Do not present any need statistic as demand for Plan B. Do not present 19.0 million students, 75.7 million volunteers or 100+ student groups as a market size for Plan B [24, 27, 28].
7. Do not call the Hope Center figures a national rate or compare them directly with GAO's [21, 23]. Do not compare the Greater Boston Food Bank's 40 percent with USDA national rates [26].
8. Do not present GAO's 650 campus pantries as a current total. It is a count from September 2018 [22].
9. Do not present the 25 million people above the income limits as an exact share of the 48 million. Use the source's words, nearly half [25].
10. Do not say the $167.2 billion measures time lost to last-minute changes. It is AmeriCorps' estimate of the value of all formal volunteering [24].
11. Do not cite VolunteerHub or Link2Feed as independent evidence of how organizers work. They are vendor framing [18, 20]. Do not equate Link2Feed's duplicate client records with Plan B's repeated warning messages.
12. Do not say that Plan B stops or prevents prompt injection. Say that its design limits what a misleading message can do [33, 37].
13. Do not say that Plan B complies with the NIST AI RMF or is certified against it, and do not say that NIST requires Plan B's roles or receipts [31, 32].
14. Do not present τ-bench's 2024 results as current agent performance, and do not merge its end-state check and pass^k into one sentence [30].
15. Do not say that the OpenAI paper proposes standing permissions. That is Plan B's own design choice [35].
16. Do not cite Anthropic's computer use page as a rule written for Plan B [36].
17. Do not put a backup hold into Jordan's projector story. The hold is shown in a separate, labelled development case.
18. Use current product names. Say Engage from Encoura, formerly Anthology Engage [16], and note that Zapier is moving Agents to AI by Zapier [7].
