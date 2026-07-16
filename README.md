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
# Scan a folder (recursively) for C2PA / AI provenance
c2pa-scanner scan ./images

# Create a signed C2PA test image (positive test fixture)
c2pa-scanner make-testimage ./test-ai.jpg
c2pa-scanner make-testimage ./test-edited.jpg --edited
```

## How it works

- **Detection:** the official `c2pa` library reads the manifest; the `digitalSourceType` assertion
  decides the verdict (`trainedAlgorithmicMedia` / `compositeWithTrainedAlgorithmicMedia` = AI).
- **Limits:** images without a manifest cannot be detected. Any resize/crop breaks the C2PA
  signature, so scan the original master, not a resized copy.

## License

Apache-2.0.
