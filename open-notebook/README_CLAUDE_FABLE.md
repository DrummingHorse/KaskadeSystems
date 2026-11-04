# README FOR CLAUDE / FABLE — THE OPEN NOTEBOOK
**Relay assignment · 2026-11-04 · Status: PROPOSAL / operator review required**

> **The experiment itself becomes the answer.**
>
> Build a public-facing reading experience for selected human–AI investigations, with the editorial discipline to show what was asked, what was tried, what failed, what was changed, and what outsiders contributed. Do not imply that a detailed process automatically proves a successful product, discovery, or theory.

## Read this first

**Canonical proposed essay:** [ARTICLE_001_THE_EXPERIMENT_ITSELF_BECOMES_THE_ANSWER.md](ARTICLE_001_THE_EXPERIMENT_ITSELF_BECOMES_THE_ANSWER.md)

**Existing repository context (read on the latest main before working):**
- [AGENTS.md](../AGENTS.md) — authority, branches, claims, amendments, commits.
- [CONTROL_ROOM.md](../CONTROL_ROOM.md) — current pointers; it is a dated snapshot, not live state.
- [README.md](../README.md) — actual static-site implementation and claims.
- [Evolution](../evolution/index.html) and [Evolution 001](../evolution/001/index.html) — existing record; **do not overwrite or rewrite**.
- Existing [styles](../styles/) and [fonts](../fonts/) — reuse where compatible.

The repo is presently **private**, but the configured website `kaskade.systems` and GitHub Pages content can be public. Nothing in this brief authorizes publication, personal disclosure, contacting others, posting to X, or merging. Draft PRs are not public launches.

## The editorial premise

There are *two simultaneous experiments* in every project:

1. **Object-level:** Does the invention, argument, artwork, service, or hypothesis hold up against appropriate evidence?
2. **Process-level:** What can be learned about the human–AI inquiry that produced and revised it?

Neither question answers the other. Treat this distinction as the product's intellectual center.

The desired reader experience is not a dashboard of AI performance claims. It is closer to an independent research notebook crossed with a thoughtful literary journal: beautiful, quiet, legible, skeptical, and hospitable to unfinished ideas.

**Keep the human visible as an agent but not personally exposed.** The author identity for public pages should be *“The KASKADE Operator”* unless the Operator explicitly approves another byline. The essay's contribution note credits human concept and direction and GPT-assisted drafting; Claude should transparently credit its later editing, design, or engineering.

## The assignment: one bounded implementation pass

After the Operator approves the public concept and content, implement a **static, reviewable Open Notebook MVP** in a new `claude/` branch and open **one PR**. No direct main push, no auto-merge.

### Suggested paths

```text
open-notebook/
  ARTICLE_001_THE_EXPERIMENT_ITSELF_BECOMES_THE_ANSWER.md  # source draft (already proposed)
  README_CLAUDE_FABLE.md                                   # this brief
  editorial/
    ENTRY_TEMPLATE.md                                      # future optional authoring template
notebook/
  index.html                                               # proposed public landing/archive
  001/
    index.html                                             # rendered essay 001
styles/
  notebook.css                                             # scoped presentation styles
```

If current site conventions favor a slightly different name, document the change in the PR rather than silently choosing an incompatible route. Do not rename or repurpose `/evolution/`. A proposed separate `/notebook/` route is intentional: Evolution is the historical operating record; the Notebook is the readable, public-facing inquiry.

### Page 1 — Notebook landing (`/notebook/`)

- A restrained hero: **“The Open Notebook”**, with subtitle **“The experiment itself becomes the answer.”**
- A short manifesto that plainly distinguishes discovery from spectacle.
- A featured link to Entry 001.
- A chronological index with date, title, subject, and **claim status** (e.g. reflection, proposal, prototype, validated finding, correction). Avoid a flashy numerical “discoveries” counter.
- Room for future categories **Ideas / Experiments / Music / Writing / Art / Responses** without pretending those sections already contain material.
- A carefully worded invitation to substantive criticism, not a claim that a conversation platform is already operating.
- A concise privacy and credit statement.

### Page 2 — Essay (`/notebook/001/`)

- Render the **entire approved essay**, not a short machine-generated summary.
- Use readable serif typography, good line lengths and leading, proper heading hierarchy, accessible links, focus states, and small-screen layout.
- Show date, version, editorial status, contribution credit, and a clear link back to the notebook.
- Provide a reserved section for **dated corrections and replies**; empty means “No reviewed responses published yet,” not fabricated engagement.
- Preserve meaningful Markdown punctuation, emphasis, blockquotes, and section order. Avoid sensational imagery or claims about AI autonomy.

### Site integration

- Use the existing static HTML/CSS pattern; do not introduce a heavy build system just to create two pages.
- Reuse existing local font files where possible. Do not add new font binaries without need or license review.
- Keep styles scoped to the notebook so Evolution and Assay pages cannot regress.
- New navigation entry on an existing public page may be proposed, **but do not alter live paths, the Evolution archive, Roots, or established claims without explicit approval**.
- No analytics, cookies, third-party scripts, lead capture, auto-posting, comment database, or external network calls in the MVP. A plain reviewed contact method may be proposed using a contact already approved by the Operator; don't invent an address.

## The recurring entry format

Later entries should use a transparent, reasonably short template:

```text
Entry number:
Title:
Date / revision:
Status: reflection | question | proposal | prototype | tested finding | correction
Public-safe description:
The observation:
The question:
What I thought initially:
Human contribution / decisions:
AI contributions (model & role, when known):
Evidence and independent checks:
Objections, failures, and alternative explanations:
Outside human input (only with permission):
What changed and why:
What remains unknown:
Next test or decision:
Sources / artifact links:
Author / editor / AI contribution note:
```

**Important:** Keep original entries and Roots intact. Corrections are appended as dated annotations or new entries, not silent edits. Cite sources when factual claims depend on them. Distinguish model-generated statements from independently verified results. Do not invent testimonials, usage numbers, visitors, pilots, endorsements, links, or causal claims.

## The external-reality gate

For every future investigation, ask:

1. What proposition is being tested?
2. What observation could change our mind?
3. Is the evidence independent of the system proposing the conclusion?
4. What did a person outside this loop actually contribute?
5. What changed as a result?
6. What, specifically, remains unproven?

Do not turn a creative reflection into a fake randomized trial. Different work requires different standards: reproducible checks for technical claims, preregistered evaluation where appropriate for scientific hypotheses, listening responses for music, editorial criticism for writing, and willingness-to-pay evidence for commercial claims.

The process itself is worth documenting; its existence is **not proof of success**.

## Privacy, intellectual property, and attribution — hard gates

**Never automatically include**:
- legal name, personal history, family, address, private contact details, finances, health, unpublished creative archives, or proprietary source code;
- private repository names or links, private messages, transcripts, confidential collaborator data, or third-party identifiers;
- patent-sensitive technical details before explicit clearance;
- full model transcripts without a line-by-line public-safe review.

Do not infer publication permission from access to the repository. Public excerpts require explicit Operator review. The Operator decides what to publish, merge, promote, and share.

Credit the human's ideas, selection, and final editorial responsibility without falsely claiming the human personally wrote generated code or prose. Credit GPT, Claude, or other model involvement accurately. No invented independent verification. No fictional quotes presented as real.

## Social channel: musings, not automation

Draft up to **three optional X posts** for review, each intelligible by itself and inviting thoughtful disagreement. Link to the site only **after** it has actually been published and verified. Never send a post or create a public reply autonomously.

A suitable initial angle:

> What if the most interesting outcome of building with AI isn't the invention, but the record of how our questions, mistakes, and judgments change? I'm opening a notebook of experiments, corrections, and unfinished ideas. What would you challenge first?

Keep a record of actual public feedback and consent before incorporating identifiable quotations. Never treat views as substantive engagement.

## Verification checklist / definition of done

In the proposed Claude PR include:

- [ ] Confirm latest `main`, open PRs/issues, and relevant existing page conventions.
- [ ] Confirm no collision with an open PR or stale branch.
- [ ] Render two pages locally: landing and full approved essay.
- [ ] Test at 375px mobile and desktop; no overflow, broken navigation, missing styles, or inaccessible headings.
- [ ] Check internal paths, canonical URLs, relative assets, and existing site integration.
- [ ] Review page source for personal info, private paths, false claims, third-party scripts, and accidental publication gates.
- [ ] Ensure every claim is labeled appropriately: **implemented**, **prototype**, **proposal**, or **metaphor** where relevant.
- [ ] Preserve Evolution history and avoid touching unrelated pages.
- [ ] Summarize own tests separately from inherited claims; include screenshots or exact commands where available.
- [ ] Keep the PR unmerged pending Operator approval.

### Completion report format

```text
Objective
Evidence read (links / main SHA / open PRs)
Changes made (paths)
Verified locally (specific checks)
Unverified / blocked
Privacy / publication review
Proposed next action
Operator approval needed?
What was not done
```

Commit messages must end with **`Relay-Pass: Claude/Constraint Architect`** (or the exact Claude role defined in the current relay). **Never force-push, auto-merge, or publish.**

## After the MVP (future proposals; do not prematurely implement)

**Stage 2 — Engagement:** opt-in external-review invitation, curated replies, rights/consent process, short “what changed after criticism” updates.

**Stage 3 — Creative gallery:** link released music, art, and writing with author-approved descriptions. Respect rights and provenance. Unreleased works remain private.

**Stage 4 — Inquiry metrics:** compare questions, corrections, evidence, finished artifacts, and outside feedback. No vanity-scoring or unsupported “intelligence growth” claims.

**Stage 5 — Monetization tests:** identify a useful problem and ask prospective buyers for an independent paid pilot, separate from editorial truth claims. No revenue promises.

## Why this matters

The intellectual ambition is deliberately modest and therefore potentially durable: keep a public record that is more honest than an announcement feed, more legible than a pile of AI transcripts, and more human than an endless exchange among models.

A good response from the world may be a collaboration, a rejection, a corrected assumption, a listener's surprise, a paying customer—or a question that changes the next experiment.

**The notebook succeeds as a record only if it preserves that difference.**

---

**Status at handoff:** GPT has proposed the founding essay and this implementation brief on a review branch. No public notebook pages, external outreach, new website route, live discussion feature, or X posts have been implemented by these two files. Approval and independent review are required before promotion to the public site.