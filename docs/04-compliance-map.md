# Compliance control map

Checked 22 August 2026. This is a technical control map, not legal advice. Policy configuration does not by itself establish compliance.

## Current dates that affect the pitch

- Regulation (EU) 2026/1744, the Digital Omnibus on AI, was published in the Official Journal on 24 July 2026 and entered into force on 27 July 2026. Annex III high-risk rules now apply from 2 December 2027; Annex I product-system rules apply from 2 August 2028. [Official Journal text](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ%3AL_202601744) and [European Commission timeline](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai).
- Article 50 transparency duties apply from 2 August 2026, subject to a limited marking/detection grace period for some systems already on the market. [European Commission Article 50 FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act).
- AI literacy obligations began applying on 2 February 2025. The 2026 omnibus simplified the duty but did not move it to the high-risk dates. [European Commission AI Act timeline](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai).
- India notified the DPDP Act commencement schedule and DPDP Rules on 13 November 2025. Consent Manager provisions commence one year after publication, on 13 November 2026; most substantive processing, rights, breach, and Significant Data Fiduciary provisions commence after eighteen months, on 13 May 2027. [Official commencement notification G.S.R. 843(E)](https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf) and [DPDP Rules 2025 G.S.R. 846(E)](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf).

## Control mapping

| Jurisdiction and obligation | ControlPlane control | Evidence emitted | Important limit |
| --- | --- | --- | --- |
| EU AI Act Article 9 risk management for applicable high-risk systems | Per-route harm vector, guarantee floor, drift scenario, review queue | Risk terms, threshold, alpha, detector evidence, override record | Whether a deployment is high-risk is a legal classification outside this gateway. |
| EU AI Act Article 12 logging | Hash-chained decision ledger with policy version | Record JSON, previous hash, record hash, timestamps | Hash chaining detects edits; it is not immutable storage or a qualified audit system. |
| EU AI Act Article 13 transparency and Article 14 human oversight | Decision reason, abstention, held effect, reviewer path | Verdict, evidence regime, effect action, reviewer override | The UI is a prototype and has no identity or role controls. |
| EU AI Act Article 50 transparency | Route policy can require AI-interaction disclosure and content marking | Policy version and disclosure flag in future adapter | The current simulator does not watermark generated content. |
| EU AI Act Article 4 AI literacy | Operational playbook and reviewer explanation | Documentation and reviewer training record outside the prototype | A software flag cannot satisfy workforce competence duties. |
| GDPR Articles 5 and 25 data minimisation and privacy by design | Prompt/output PII detection, route retention, effect gating | PII signal, consent flag, retention days | Regex stubs do not ensure all personal data is detected. |
| GDPR Articles 30 and 32 records and security | Versioned policy and audit chain | Processing-route trace and integrity check | Controller/processor records and security measures extend beyond AI decisions. |
| India DPDP notice and consent duties | Consent-required policy field and jurisdiction resolution | Consent requirement, policy hash, retention | Consent capture and withdrawal are not implemented. |
| India DPDP breach duties | PII and exfiltration signals, incident outcome feedback | Detection evidence and incident link | Notification workflows and statutory clocks are not implemented. |
| India Significant Data Fiduciary audit and assessment duties | Reproducible evaluation, ledger, override history | Generated report and versioned records | The prototype is not an independent data auditor or impact assessment. |
| HIPAA Security Rule risk analysis and audit controls | Health route can require stricter holds and activity logging | Risk terms, effect action, audit chain | No HIPAA route ships yet; hosting, BAAs, access control, and ePHI safeguards are outside scope. |

GDPR text is available in the [consolidated regulation](https://eur-lex.europa.eu/eli/reg/2016/679/oj). HIPAA's Security Rule requires administrative, physical, and technical safeguards for ePHI, and its audit-controls standard requires mechanisms to record and examine relevant system activity. See the [HHS Security Rule summary](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html) and [HHS audit protocol](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/protocol/index.html).

## Why policy is configuration

The EU dates moved in July 2026, while India's staged commencement creates different control dates in November 2026 and May 2027. `config/policies/*.yaml` therefore carries jurisdiction values, a human-readable version, and a content hash. Every decision record stores both. Production would add effective-from/effective-to dates, signed releases, migration checks, and dual approval.

