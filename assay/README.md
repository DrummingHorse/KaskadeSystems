# PROSPEKTOR Assay Office

Pilot-stage landing page at `https://kaskade.systems/assay/`, integrated into the existing Kaskade homepage and Evolution index. Static HTML, inline CSS and JavaScript, self-hosted fonts, no build step.

## Current status — 29 October 2026

- The only test so far is one 50-case synthetic benchmark. No real-world accuracy or commercial usefulness has been established.
- Pilots are tool-assisted and human-reviewed.
- No signed certificates, live umpire assays, or ERC-8183 / ERC-8004 integration are available.
- Protocol, reputation, and settlement descriptions are proposed designs.

## Integration scope

The supplied landing-page copy and visual specimens were retained for the requested skeptical buyer review. The integration adds a prominent current-status note, a collaboration invitation, and navigation to Kaskade; it configures the existing request form to use `kaskade.systems@gmail.com`. These additions do not resolve every copy issue identified in the review.

The request form composes an email in the visitor's mail app. It does not send mail itself or upload files. Collaboration links also compose email; no messages are sent by the website.

The existing `noindex, nofollow` directive remains in place. The page is publicly reachable from Kaskade, while the directive asks search engines not to index it.

## Development priorities

1. Review the present-tense archive, hashing, model-independence, and protocol claims against implemented behavior.
2. Publish an inspectable benchmark method, scoring criteria, results, and failure cases before making performance claims.
3. Clarify the limits of freshness and cross-delivery originality checks.
4. Define retention for email attachments and archived sources, and clarify permission to publish anonymized pilot results.
5. Test real deliverables with collaborators; distinguish proposed work, completed tests, and demonstrated results in every update.

The supplied three-business-day turnaround, five free pilot places, deletion language, and feedback terms remain the operator's service commitments. This deployment does not automate fulfillment or retention.

## Validation

Local links, fragment targets, unique IDs, asset signatures, the email form's recipient and encoding, and demo replay were checked. The page and collaboration section were also inspected in the browser preview.

## Assets

`favicon.svg`, `og.png`, and the `fonts/` directory belong with `index.html`. Font license files are included. `.nojekyll` is retained from the supplied bundle.
