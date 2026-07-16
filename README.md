# c2pa-scanner

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <b>English</b> &middot;
  <img src="docs/flags/de.svg" height="13" alt=""> <a href="README.de.md">Deutsch</a>
</p>

---

Detects the **C2PA provenance manifest** in images and flags the ones that are
**AI-generated** - so you can label them as required by the EU AI Act (Art. 50).

It reads the `digitalSourceType` from a C2PA manifest (e.g. embedded automatically by Adobe /
Firefly) and classifies each image: AI-generated, AI-edited, other provenance, or none.

## What this tool is for - and what it is not

> **This tool checks your own images and pages** for AI labeling under the EU AI Act and
> makes them compliant - nothing more.
>
> It is **explicitly NOT** meant to scan third-party websites, collect violations and turn them
> into cease-and-desist letters. If that is your plan, you are in the wrong place.
>
> For context: the C2PA scan is only an **indicator** - it only finds images that carry a
> provenance manifest (e.g. Adobe / Firefly), never all AI images. It is not legal advice and not
> proof of a violation. Use it fairly.
>
> **Legal basis:** EU AI Act (Regulation (EU) 2024/1689), in particular Article 50 (transparency
> obligations), applicable from 2 August 2026.
> Legal text (EUR-Lex): https://eur-lex.europa.eu/eli/reg/2024/1689/oj
> Article 50 (readable): https://artificialintelligenceact.eu/article/50/

## Usage

```bash
# Launch the graphical TUI (default when no command is given)
c2pa-scanner
c2pa-scanner tui https://www.example.com/sitemap.xml

# Crawl a sitemap and check every image for C2PA / AI provenance (a bare domain
# works too - the sitemap is then discovered automatically)
c2pa-scanner scan https://www.example.com/sitemap.xml
c2pa-scanner scan ./sitemap.xml

# Create a signed C2PA test image (positive test fixture)
c2pa-scanner make-testimage ./test-ai.jpg
c2pa-scanner make-testimage ./test-edited.jpg --edited
```

## How it works

Detection is layered and deliberately tuned for few false positives:

- **C2PA manifest** (primary signal): the official `c2pa` library reads the signed manifest; the
  `digitalSourceType` assertion decides the verdict (`trainedAlgorithmicMedia` = AI-generated,
  `compositeWithTrainedAlgorithmicMedia` = AI-edited).
- **XMP/EXIF `digitalSourceType`** (secondary signal): the same IPTC marker is also read from XMP when
  there is no valid C2PA - this catches images that lost their signature on resize but kept the XMP.
- **Generating tool** (fallback): if there is no `digitalSourceType` at all, the `Software` /
  `CreatorTool` tag is matched against a curated list of unambiguous generative-AI tools (Midjourney,
  DALL-E, Stable Diffusion, Adobe Firefly, ...). Ambiguous editors like Photoshop or GIMP are
  deliberately NOT on the list, to avoid false positives.
- **Page crawl:** all pages from a sitemap are fetched and image URLs are extracted via regex over the
  raw HTML - this also finds images in web-component attributes / shadow DOM, not just classic
  `<img src>`. If no direct sitemap URL is given, it is discovered automatically (robots.txt, then
  common paths).

**Limits:** images with no provenance signal at all (no C2PA, no XMP/EXIF) cannot be flagged as AI.
Metadata can be stripped - screenshots, re-saving, and many platforms remove it on upload. A hit is a
solid indication **for** AI; its absence is **not** proof against it. Any resize/crop breaks the C2PA
signature, so scan the original master where possible.

### Other detection methods - and why they are (not yet) implemented

For completeness, the alternatives that exist but are deliberately NOT built in:

- **Invisible watermarks** (Google SynthID, Meta, Amazon Titan): robust against edits, but each scheme
  needs its vendor's own detector - there is no open, universal reader. SynthID can only be checked via
  Google's own portal, not as a library. **Reason: not integrable.**
- **ML classifiers** ("is this AI?", e.g. Hive, Sensity, Illuminarty): unreliable across generators and
  after compression/resize (high false-positive AND false-negative rates), age quickly, adversarially
  fragile. **Reason: not defensible for a labeling decision** - it would undermine the solid verdict; at
  most conceivable as a separately flagged "uncertain hint" that does not drive the result.
- **Forensics/statistics** (frequency spectrum, noise residuals, diffusion fingerprints): research-grade,
  no turnkey tool, same reliability caveats as ML classifiers. **Reason: effort vs. value does not add
  up.**
- **Fingerprint/hash matching** against a registry of known AI images: only works if the image is
  registered there - not a general solution. **Reason: coverage too low.**

The guiding principle: prefer a few solid signals (provenance) over many uncertain ones - fitting the
purpose of supporting compliant AI labeling under EU AI Act Art. 50.

## License

Apache-2.0.
