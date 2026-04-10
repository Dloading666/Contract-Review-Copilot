# Design System Specification

## 1. Overview & Creative North Star: "The Analog Architect"

The design system is a radical departure from the sanitized, "soft" interfaces of the modern web. Its **Creative North Star is "The Analog Architect."** It celebrates the raw, structural integrity of architectural blueprints combined with the playful, high-contrast rebellion of 1990s fanzines. 

This is "Neo-Brutalism" executed with editorial precision. We move beyond generic templates by utilizing **intentional asymmetry**, **aggressive stroke weights**, and a **warm, archival base palette**. By rejecting the 1px border and the rounded corner, we create an interface that feels tactile, authoritative, and unapologetically digital. The user should feel they are interacting with a high-end physical machine rather than a fleeting web app.

---

## 2. Colors & Surface Logic

### The Palette
The color strategy relies on a "High-Contrast Earthy" foundation. We use a warm off-white (`surface`: #f7f7f2) to reduce eye strain while allowing our vibrant primary and secondary accents to "pop" with maximum intensity.

*   **Primary (Action/Success):** `#006a35` (Deep Green) / `#6bfe9c` (Vibrant Neon Green)
*   **Secondary (Attention/Warning):** `#825000` (Deep Amber) / `#ffc787` (Bright Orange)
*   **Surface:** `#f7f7f2` (The Paper Base)
*   **On-Surface:** `#2d2f2c` (The "Ink" Black)

### The "No-Thin-Line" Rule
Standard 1px borders are strictly prohibited. They represent indecision. In this system, boundaries are defined in two ways:
1.  **Bold Structural Lines:** Use 3px to 5px solid `#2d2f2c` borders for primary containers and inputs.
2.  **Tonal Sectioning:** Use background shifts (e.g., a `surface-container-low` section sitting on a `surface` background) to define large content areas without adding visual noise.

### Surface Hierarchy & Nesting
Treat the UI as stacked sheets of heavy cardstock.
*   **Lowest Layer:** `surface` (#f7f7f2).
*   **Mid Layer:** `surface-container` (#e8e9e3) for sidebar backgrounds or inactive regions.
*   **Top Layer:** `surface-container-highest` (#dcddd7) for active cards and focused content.
*   **Signature Textures:** For Hero sections or primary CTAs, apply a subtle linear gradient from `primary` to `primary_container` at a 135-degree angle to add "soul" to the flat Neo-Brutalist shapes.

---

## 3. Typography: The Brutalist Typewriter

We utilize a high-contrast pairing that balances technical precision with modern readability.

*   **Display & Headlines (Space Grotesk):** This is our "Architect" font. It is wide, bold, and commands attention. All Display and Headline styles must be set with `fontWeight: 700` and `letterSpacing: -0.02em`.
*   **Body & Titles (Work Sans):** Our "Workhorse." It provides the legibility required for complex contract review.
*   **The Editorial Scale:** 
    *   **Display-LG (3.5rem):** Used for large numerical data or hero headers.
    *   **Headline-SM (1.5rem):** The standard for card titles and section headers.
    *   **Label-MD (0.75rem):** Always set in Space Grotesk Bold, often All-Caps, for a technical, "meta-data" aesthetic.

---

## 4. Elevation & Depth: The Flat-Shadow Principle

In this system, we do not simulate light; we simulate **graphic impact**.

*   **The Layering Principle:** Depth is achieved through `surface-container` nesting. An inner box should always be a tier higher (lighter) or lower (darker) than its parent to signify hierarchy.
*   **Hard Shadows (The Signature):** For floating elements like buttons or active cards, use a **flat, 100% opaque shadow**.
    *   *Specification:* `box-shadow: 4px 4px 0px 0px #0d0f0c;`
    *   This creates a "sticker" effect that feels intentional and premium.
*   **The Ghost Border Fallback:** For disabled states or secondary info, use `outline-variant` at 20% opacity. Never use a 100% opaque thin line.
*   **Glassmorphism Integration:** For overlays (Modals/Tooltips), use `surface_container_lowest` at 85% opacity with a `backdrop-filter: blur(12px)`. This softens the brutalism and adds a "High-End Editorial" layer of sophistication.

---

## 5. Components

### Buttons
*   **Primary:** Background `#2ecc71` (Green), 3px Black Border, Flat 4px Shadow. Text: Space Grotesk Bold.
*   **Secondary:** Background `#f39c12` (Orange), 3px Black Border, Flat 4px Shadow.
*   **Interaction:** On `:hover`, the button should move `2px` down and right, and the shadow should decrease by `2px` to simulate a physical "press."

### Input Fields
*   **Base:** 3px black border, sharp 0px corners, `#ffffff` background.
*   **Focus State:** The border remains 3px but changes to `primary`. A flat shadow (4px) appears behind the field to indicate "active entry."
*   **Validation:** Use `error` (#b31b25) for borders, but keep the 3px weight.

### Cards & Lists
*   **Rule:** Forbid divider lines. Use vertical white space (32px or 48px) to separate items.
*   **List Item:** Use a `surface-container-low` background on `:hover` to highlight rows.

### Retro-Pixel Illustrations
All icons and status illustrations must utilize a **pixel-art aesthetic**. This anchors the "Analog Architect" theme, providing a nostalgic, human touch to a high-tech assistant. Icons should be 24px grid-aligned but rendered with chunky, 2px-scaled pixels.

---

## 6. Do’s and Don’ts

### Do:
*   **DO** use sharp 0px corners for everything. No exceptions.
*   **DO** lean into asymmetry. A sidebar can be significantly wider than a standard grid if it aids the editorial flow.
*   **DO** use "Ink Black" (#2d2f2c) for all text to maintain high contrast against the warm off-white.

### Don’t:
*   **DON'T** use 1px borders. They make the design look like a "bootstrap" template.
*   **DON'T** use soft, blurry drop shadows. They contradict the Neo-Brutalist honesty of the system.
*   **DON'T** use pastel colors. Our accents must be vibrant and "loud" to compete with the heavy black structural elements.
*   **DON'T** center-align everything. Use strong left-alignment to mimic the structure of a technical document or a newspaper.