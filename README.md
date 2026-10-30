# Kaskade

**Proposal:** this pass prepares a clearer public presentation of Assay Office by Kaskade, the name selected by Graham for the pilot. Graham decides what becomes canon by merging the pull request.

## Relay workflow

The Operator's rules are in [AGENTS.md](AGENTS.md). Start from latest main, read open PRs, use a model-prefixed branch, include the relay footer on every commit, preserve Evolution entries and research Roots, and deliver one PR per task.

## Implemented

Static pages, local fonts, navigation, social-preview metadata, and email-drafting links are implemented in this checkout. No frontend build is required. Source changes in this branch are not a production deployment until the Operator merges them.

Current contact: `kaskade.evolution@gmail.com`. Email links and the pilot form compose drafts; they do not establish inbox delivery or monitoring.

The original Evolution pages are preserved. The Evolution index has only an added dated Annotation notice and its scoped stylesheet. Corrections and context are in `/evolution/annotations/2026-10-30-gpt-public-presentation/`.

## Prototype

The report specimens use fictional firms. The recorded code test is an offline, deterministic 50-case synthetic benchmark. Its complete fictional registry made the fixture too easy to establish live-source accuracy or semantic judging. Customer usefulness and willingness to pay remain unvalidated.

## Proposal

The public name selected by Graham is Assay Office by Kaskade. It is implemented throughout the current presentation in this branch and awaits merge for publication. Free human-reviewed pilots, scope, timing, and data-sharing arrangements remain proposals to agree with participants. SKRAPR, Architekt, cross-provider judging, signed certificates, dispute rulings, and payment/reputation integrations are not represented as shipped services.

## Metaphor

Gold, pyrite, and assay terminology provide an analogy for checking work; they are not accreditation or a guarantee of truth, conversion, or value.

## Implemented routes and assets

- `/`: presentation, labelled specimen, evidence links, and collaboration routes.
- `/assay/`: pilot proposal, prototype specimen, recorded benchmark, and email-drafting form.
- `/evolution/annotations/2026-10-30-gpt-name-and-contact/`: new dated Annotation recording Graham's name selection and confirmed contact without rewriting the earlier naming proposal.
- `/evolution/`: preserved development archive with an added dated Annotation notice.
- `/evolution/001/`: unchanged historical article.
- `/evolution/annotations/2026-10-30-gpt-public-presentation/`: new status and naming Annotation.

Legacy homepage anchors `#method`, `#skrapr`, `#architekt`, `#evolution`, `#assay`, and `#access` are retained.

The shared social preview is rendered by `tools/render-social-card.py` using Pillow and fontTools. Python Brotli or Node's built-in decoder supports the bundled WOFF2 fonts. The image contains no customer or performance claims.
