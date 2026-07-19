# Data Processing Addendum (TEMPLATE)

> **THIS IS A TEMPLATE FOR LEGAL REVIEW — NOT AN EXECUTED AGREEMENT.**
>
> It is an engineering-supplied starting point that reflects how the Simulation
> Labs platform actually handles data (see [`docs/data-policy.md`](./data-policy.md)).
> It has **not** been reviewed by counsel and is **not** legal advice. Do not
> sign, send, or represent it as a binding contract until a qualified attorney
> has reviewed and adapted it to the governing law, the customer, and the
> executed master agreement. Bracketed `[…]` fields are placeholders.

This Data Processing Addendum (the "**DPA**") supplements the agreement between
the parties for the use of the Simulation Labs platform (the "**Agreement**")
and governs the processing of Personal Data by Simulation Labs on the
Customer's behalf.

Simulation Labs is a **behavioral / conversion-testing** platform: it runs
swarms of mechanically-degraded synthetic personas against a Customer's live
website to measure where a conversion flow (sign-up, checkout, cancel) breaks
down. Because those personas act on a real web application and the platform
records the sessions, the recordings can contain Personal Data.

---

## 1. Parties and roles

| | |
|---|---|
| **Data Controller** | `[Customer legal entity, address]` — determines the purposes and means of processing. |
| **Data Processor** | `[Simulation Labs legal entity, address]` — processes Personal Data only on the Controller's documented instructions. |
| **Effective date** | `[date]` |
| **Governing agreement** | The `[Master Services Agreement / Terms of Service]` dated `[date]`. |
| **Governing law / regime** | `[e.g. GDPR (EU/EEA), UK GDPR, CCPA/CPRA]` |

For processing subject to the GDPR, the Customer is the **controller** and
Simulation Labs is the **processor** (or, where applicable, sub-processor). For
CCPA/CPRA, Simulation Labs acts as a **service provider** and does not sell or
share Personal Data.

---

## 2. Subject matter, duration, nature and purpose

- **Subject matter:** provision of the Simulation Labs behavioral-testing
  service under the Agreement.
- **Nature and purpose:** executing automated persona runs against the
  Customer's designated target website, capturing the resulting session
  artifacts, and producing survival curves, abandonment heatmaps, video
  receipts, and synthetic exit-interview audio for the Customer's analysis.
- **Duration:** for the term of the Agreement, plus the retention windows in
  §6, after which data is deleted.

---

## 3. Categories of data subjects

- The Customer's end users whose data happens to render on the target site
  during a run (e.g. if a persona reaches a logged-in page or a confirmation
  screen showing real data).
- The Customer's own personnel who hold Simulation Labs accounts (authorized
  users / project members).

> **Important:** Simulation Labs advises Customers to run swarms against staging
> environments or accounts seeded with **synthetic** data wherever possible, to
> minimize incidental capture of end-user Personal Data (see
> [`docs/data-policy.md`](./data-policy.md) §1).

---

## 4. Categories of Personal Data

Derived from the platform's data inventory ([`docs/data-policy.md`](./data-policy.md) §1):

| Category | Description | Sensitivity |
|----------|-------------|-------------|
| **Run screenshots** | Frame-by-frame captures of the target site; may contain any Personal Data rendered on screen. | High / potentially PII-bearing |
| **Run video (`.webm`)** | Full session recordings of the flow; same exposure as screenshots, continuous. | High / potentially PII-bearing |
| **Reports (`report.json`/`.html`, heatmap PNG)** | Survival curves, abandonment coordinates, captions; may embed screenshot thumbnails. | Medium (treat as screenshot-equivalent) |
| **Exit-interview audio (`.wav`)** | Synthetic (Gradium) voice narrating a persona's own action trace. No end-user voice. | Medium |
| **Run metadata** | `target_url`, task, flow name, persona ids, completion rate, timestamps, report JSON. | Medium |
| **Account data** | Authorized-user email and password hash (bcrypt/SHA — no plaintext). | Medium |
| **Project / billing identifiers** | Project names, tiers, ownership, Stripe customer/subscription ids and billing email. No card data (Stripe is system of record). | Low–Medium |

The parties acknowledge that **run screenshots and video are the most sensitive
class**, because whatever renders on the target site during a run is captured in
the pixels. The Customer is responsible for the lawful basis of any Personal
Data present on the target site it directs Simulation Labs to test.

Special-category data (GDPR Art. 9) should not be introduced into runs; if the
Customer's target site processes such data, the Customer must disclose this and
the parties must agree additional safeguards in writing before runs execute.

---

## 5. Sub-processors

The Customer authorizes Simulation Labs to engage the sub-processors below.
Simulation Labs maintains data-processing terms with each and will give the
Customer prior notice of any intended change (addition or replacement), with an
opportunity to object, per §11.

| Sub-processor | Purpose | Data shared |
|---------------|---------|-------------|
| **H Company (Holo Models API)** | Persona perception/decision — the vision model reads each screenshot and returns the next action. | Perturbed screenshots of the target site (base64 image parts). This is how site pixels leave Simulation Labs infrastructure; scoped to the run. |
| **Gradium** | Text-to-speech for exit-interview audio. | Model-generated interview text derived from the action trace. No end-user audio. |
| **Anthropic (Claude)** | Turns a persona's action trace into a first-person exit-interview narrative. | The action trace + run context (text). |
| **Stripe** | Billing and payments; system of record for payment instruments. | Customer/subscription identifiers, billing email. No full card data. |
| **Object storage (AWS S3 or S3-compatible)** | Durable storage of run artifacts and database backups. | All run artifacts + backups. |
| **NVIDIA NemoClaw / OpenShell** *(optional)* | Policy gateway that Holo inference may be routed through, when configured. | Same screenshots as the Holo path, when enabled. |

Simulation Labs remains liable for its sub-processors' performance of their data
protection obligations to the same extent as if it performed them itself.

---

## 6. Data retention and deletion

Per [`docs/data-policy.md`](./data-policy.md) §2–3:

- **Run artifacts and metadata:** default retention **90 days** from creation,
  then deleted by `ops/retention.py` (artifacts + row). Enterprise ("audit")
  tiers may negotiate a shorter (e.g. 24–72h) or longer window.
- **Database backups:** **30-day** rolling window.
- **Accounts, projects, memberships, API keys:** kept for the life of the
  account; deleted on closure or verified request.
- **Deletion on request (GDPR Art. 17 / CCPA):** actioned within **30 days** of
  a verified request; artifact deletion typically same-day. Deleted data may
  persist in encrypted backups only until those backups age out of the 30-day
  window, after which it is unrecoverable.
- **On termination:** upon expiry or termination of the Agreement, Simulation
  Labs will, at the Customer's choice, delete or return all Personal Data and
  delete existing copies, subject to the backup window above and any legal
  retention obligation.

---

## 7. Security measures

Simulation Labs implements appropriate technical and organizational measures,
including those below (see [`docs/data-policy.md`](./data-policy.md) §4 and the
our internal SOC 2 readiness matrix for current maturity):

- **Encryption in transit:** TLS for all client↔server and server↔sub-processor
  traffic.
- **Encryption at rest:** server-side encryption expected on the object-storage
  bucket and encrypted database volumes (operator-configured — see the SOC 2
  readiness matrix for the current gap).
- **Access control:** per-project tenant isolation; authenticated,
  scope-checked API routes; artifacts served only via an authenticated route
  with short-lived signed URLs; passwords hashed with bcrypt; API keys stored
  only as hashes.
- **Secrets:** provided via environment / secrets manager; never committed.
- **Logging:** structured per-request access logs with request ids and no
  secrets; metrics and SLO-based alerting.
- **SSRF protection:** run target URLs are validated to block private/metadata
  addresses at enqueue.

The parties acknowledge Simulation Labs is **not yet SOC 2 certified**; the
readiness matrix honestly
states which controls are Implemented, Partial, or Not-started.

---

## 8. Data-subject rights

Simulation Labs will, taking into account the nature of the processing, assist
the Customer by appropriate technical and organizational measures — insofar as
possible — in fulfilling the Customer's obligation to respond to data-subject
requests to exercise rights of access, rectification, erasure, restriction,
portability, and objection (GDPR Ch. III; CCPA/CPRA equivalents). Because
Simulation Labs processes data on the Customer's instructions, requests received
directly from a data subject will be referred to the Customer, and Simulation
Labs will action Customer-directed deletion/erasure via the mechanisms in §6.

---

## 9. Personal-data breach notification

Simulation Labs will notify the Customer **without undue delay and in any event
within `[72] hours`** after becoming aware of a Personal Data breach affecting
the Customer's data, and will provide (as it becomes available): the nature of
the breach, categories and approximate volume of data and data subjects
affected, likely consequences, and the measures taken or proposed to address it.
Simulation Labs will reasonably cooperate with the Customer's own notification
obligations to supervisory authorities and data subjects. See the
responsible-disclosure channel in [`docs/security-disclosure.md`](./security-disclosure.md)
and our internal incident-response process.

---

## 10. International transfers

Where Personal Data subject to the GDPR/UK GDPR is transferred outside the
EEA/UK to a country without an adequacy decision, the parties will rely on the
appropriate transfer mechanism (e.g. the EU **Standard Contractual Clauses** and
the **UK Addendum**), which are incorporated by reference and completed at
`[Annex — SCC module and details to be completed by counsel]`. Customers should
confirm the processing locations of the sub-processors in §5.

---

## 11. Sub-processor changes and audit

- **Change notice:** Simulation Labs will give at least `[30] days'` notice
  before adding or replacing a sub-processor; the Customer may object on
  reasonable data-protection grounds within `[14] days`, and the parties will
  work in good faith to resolve the objection.
- **Audit:** Simulation Labs will make available information reasonably
  necessary to demonstrate compliance with this DPA and, on reasonable notice
  and no more than `[once per year]` (or after a breach), allow for and
  contribute to audits — which may be satisfied by providing a third-party
  attestation (e.g. a SOC 2 report) once available.

---

## 12. General

- **Instructions:** Simulation Labs processes Personal Data only on the
  Customer's documented instructions (including this DPA and the Agreement),
  unless required by law, in which case it will inform the Customer unless
  legally prohibited.
- **Confidentiality:** personnel authorized to process Personal Data are bound
  by confidentiality.
- **Precedence:** in case of conflict on data-protection matters, this DPA
  prevails over the Agreement.
- **Governing law:** as set out in the Agreement / `[jurisdiction]`.

---

*Signature blocks, annexes (SCCs, technical-and-organizational-measures detail),
and jurisdiction-specific clauses to be completed under legal review before
execution.*

Contact for data-protection matters: `privacy@simulationlabs.example` (replace
with the production address).
