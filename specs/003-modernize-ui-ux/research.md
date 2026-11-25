# Research: Modernize UI and UX

**Date**: 2026-11-24
**Scope**: Presentation and verification choices for [spec.md](./spec.md).

## 1. Styling library and delivery

**Decision**: Vendor Bootstrap 5.3.9's compiled minified CSS and full MIT license;
load the local CSS before the existing application stylesheet. No Bootstrap JS,
Popper, component library, Sass compilation, or frontend package manager.

**Rationale**: The existing application is a FastAPI-served HTML page with native
JavaScript modules. Bootstrap provides compiled grid, forms, buttons, cards, and
alerts without requiring a new build pipeline. This meets the explicit library
request while keeping Python packaging and execution managed by uv.

**Alternatives considered**:

- Tailwind: valid offline, zero-runtime option, but requires class scanning and a
  compilation step, through npm or its standalone executable. Not justified for
  three existing views when compiled Bootstrap satisfies current needs.
- A component library: no current need for complex widgets. Adds behavior,
  dependencies, and accessibility verification without clear benefit.
- Runtime CDN or Tailwind browser compilation: incompatible with offline runtime
  and existing local resource/security constraints.
- More bespoke CSS alone: does not satisfy the user's library request.

**Verified sources**:

- [Bootstrap download documentation](https://getbootstrap.com/docs/5.3/getting-started/download/)
  identifies compiled 5.3.9 assets and the official release archive:
  `https://github.com/twbs/bootstrap/releases/download/v5.3.9/bootstrap-5.3.9-dist.zip`.
- The documented SHA-384 for upstream `bootstrap.min.css` is
  `yEPZ7jP9S0QKiUQ0m3jjsO4ProIW7wvR9gXkI7JOGa2XVsw53Yke2bsdkBbjmmiX`.
  Verify locally before vendoring; never send repository files to a checksum website.
- [Bootstrap license guidance](https://getbootstrap.com/docs/5.3/about/license/)
  requires preserving copyright/license notices and permits licensed redistribution
  and modification. Obtain the full license from the
  [versioned upstream license](https://github.com/twbs/bootstrap/blob/v5.3.9/LICENSE).
- [Tailwind CLI documentation](https://tailwindcss.com/docs/installation/tailwind-cli)
  confirms its generated-CSS workflow and standalone executable alternative.

**Asset policy**: Keep upstream notices intact. If omitting the source map, remove
only its trailing `sourceMappingURL` comment after verifying upstream bytes and record
both original verification and shipped checksum in README. No CSS functionality edits
to vendor code; customization stays in `styles.css`. Check packaged-wheel contents.

## 2. Accessibility and security-compatible controls

**Decision**: Use semantic native controls with explicit labels, field-associated
messages, `aria-invalid`, selected navigation, visible focus, and textual statuses.
Retain CSP without `unsafe-inline`, `data:`, or remote exceptions. Existing control
behavior stays in scope; formal accessibility review is no longer a release gate.

**Rationale**: Bootstrap is styling, not proof of accessibility.
[Upstream accessibility guidance](https://getbootstrap.com/docs/5.3/getting-started/accessibility/)
warns that some default palettes fail text/non-text contrast. Its
[validation documentation](https://getbootstrap.com/docs/5.3/forms/validation/)
warns that visual custom-validation styles/tooltips alone are not accessible.
Pair any invalid styling with persistent textual feedback and field associations.

Bootstrap's [select styles](https://getbootstrap.com/docs/5.3/forms/select/) embed
SVG indicators as data URLs, which the current `default-src 'self'` policy does not
allow. Override used select/validation backgrounds to avoid embedded images and
restore native select appearance; do not loosen CSP. Use no Bootstrap JS widgets
or icon font. Put all theme declarations in an external stylesheet.

**Alternatives considered**: Default palette without review; tooltip-only errors;
relaxing CSP for decorative images; custom dropdown widgets. Each either risks
noncompliance or is more complex than native controls.

**Compatibility detail**: Bootstrap display utilities can override native hidden
states. Add a final `[hidden] { display: none !important; }` rule and exercise every
hidden view/control. Import forced navigation occurs repeatedly during polling:
focus changes only when the visible area actually changes.

## 3. Layout and transaction details

**Decision**: A light, neutral application shell with an accent primary action,
clearly selected navigation, Bootstrap grid-based form groups, and readable cards.
Use one semantic article per occurrence, laid out in aligned columns on wide screens
and stacked labeled values on narrow screens. Inline source details include selected
date, exact amount/currency, a close action, and a retry action on retrieval failure.

**Rationale**: Preserves existing article-based list and button semantics without
duplicated desktop/mobile representations. Inline details avoid focus traps,
overlay scrolling, and additional JS dependencies. Occurrence ID remains identity;
visible fields are not unique.

**Alternatives considered**: Separate mobile cards/desktop table (duplicates state
and controls); modal/offcanvas details (adds focus/lifecycle complexity); entirely
unstructured paragraphs (insufficient scanability).

**Interaction decisions**: Opening details focuses a stable detail heading and
retains its selected context during loading/failure. Closing returns focus to the
actual initiating control if still connected and visible. Filter/page changes clear
details and invalidate old responses. Show a distinct applied-filter summary so
editing form fields without Apply never mislabels existing results.

## 4. Preserve workflow, financial, and integration contracts

**Decision**: Derive visual status kind from structured existing state and safe
notices, never from message-text matching. Preserve state transitions, opaque
request IDs, exact amount formatting/parsing, pagination, and response-generation
guards. Add no endpoints, migrations, monetary totals, analytics, or model calls.

**Rationale**: Existing `import.js` distinguishes confirmed failures from unknown
outcomes and holds navigation until safe. `transactions.js` already uses strings
and BigInt for exact amounts and text nodes for untrusted evidence. Those mechanisms
are dependencies to preserve, not rewrite for cosmetic convenience.

**Alternatives considered**: A new shared application store, richer server endpoints,
or optimistic financial summaries. All exceed this presentation scope.

## 5. Verification

**Decision**: Use integrated-browser playground checks and maintainer approval for
UI usability. Retain asset/unit and real-PostgreSQL tests as required engineering
checks. Existing browser/E2E tests and optional browser-channel support remain
available, but are not feature gates.

**Rationale**: The maintainer considers the current interface usable for their own
use and explicitly waived browser-runner and formal acceptance/study requirements.
Mocked playground responses do not prove real security headers; existing ASGI
asset/security tests retain that contract verification.

**Alternatives considered**: Required browser provisioning, exhaustive acceptance
matrices, and five-person studies were rejected for this feature. Use synthetic
information, not live financial inputs.

The approved, feature-scoped constitutional verification exception and its resolution
condition are documented in [spec.md](./spec.md#scoped-verification-exception-approved-2026-11-24).
