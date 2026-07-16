# C2PA-Scanner (PoC) - Plan

Stand: 16.07.2026. Loser Bezug: JIRA DMZ-17235 (KI-Label, EU AI Act Art. 50).

**Zwei getrennte Geschichten:**

1. **C2PA-Scanner (DIESES Repo):** eigenstaendiger Proof of Concept, **unabhaengig
   von Sitefinity**, generisch verwendbar. Privates GitHub-Repo, Python/Textual.
   Erkennt in Bildern den C2PA-Herkunftsnachweis und filtert die KI-generierten
   heraus.
2. **Sitefinity-Dashboard-Widget (SPAETER, eigener Task, NICHT dieses Repo):**
   .NET Framework 4.8, durchsucht gezielt alle Sitefinity-**Bibliotheken**
   (keine Seiten). Nutzt die Erkenntnisse aus dem PoC. Ausserhalb dieses Plans.

---

## Ziel (Story 1)

Ein generischer C2PA-Detektor als TUI/CLI: gib ihm Bilder (lokaler Ordner
und/oder URL-Liste), er sagt dir pro Bild, ob ein C2PA-Manifest drinsteckt und
ob es KI-Herkunft ausweist. Kein Sitefinity, kein Seiten-Crawl.

**Positionierung:** Selbstpruef-Werkzeug, um die EIGENEN Seiten (enviaM, privat,
spaeter ggf. corporate/E.ON) rechtssicher/"bulletproof" zu machen. Michael nutzt
es auch privat. KEIN Fremd-Scan-Werkzeug.

## DISCLAIMER (VERPFLICHTEND in README UND About-Dialog, fett)

Reader-Text -> echte Umlaute (ä ö ü ß). Kanonischer Wortlaut:

> **Wofür dieses Tool gedacht ist - und wofür nicht**
>
> Dieses Tool ist ein **Selbstprüf-Werkzeug**. Es hilft dir, deine **eigenen**
> Bilder und Seiten auf die KI-Kennzeichnung nach dem EU AI Act zu prüfen und
> rechtssicher zu machen - nicht mehr und nicht weniger.
>
> Es ist **ausdrücklich NICHT** dazu gedacht, fremde Webseiten zu durchleuchten,
> Verstöße zu sammeln und daraus Abmahnungen zu basteln. Wer das damit vorhat,
> ist hier falsch.
>
> Zur Einordnung: Der C2PA-Scan ist nur ein **Indiz** - er findet ausschließlich
> Bilder mit Herkunfts-Manifest (z.B. Adobe/Firefly), niemals alle KI-Bilder. Er
> ist kein Rechtsgutachten und kein Beweis für einen Verstoß. Nutze ihn fair.
>
> **Rechtsgrundlage:** EU AI Act (Verordnung (EU) 2024/1689), insbesondere
> Artikel 50 (Transparenzpflichten), gültig ab 2. August 2026.
> Gesetzestext (EUR-Lex): https://eur-lex.europa.eu/eli/reg/2024/1689/oj
> Artikel 50 (lesbar): https://artificialintelligenceact.eu/article/50/

About-Dialog: als eigener Absatz/eigene Sektion, fett hervorgehoben; der
EUR-Lex-Link als Hover-klickbarer Link (ClickableLinksMixin).

---

## Kritische Erkenntnisse (technisch, generisch)

1. **"Hat C2PA" != "ist AI".** C2PA kann reine Kamera-Provenienz sein. Manifest
   lesen und `c2pa.digitalSourceType` klassifizieren:
   - `trainedAlgorithmicMedia` = voll KI-generiert -> Verdict AI
   - `compositeWithTrainedAlgorithmicMedia` = KI-bearbeitet -> Verdict AI
   - alles andere (Kamera etc.) -> Verdict kein-AI
   Datenbasis fuer die Verdict-Spalte, kein Raten.
2. **C2PA-Scan ist eine Untergrenze.** Nur Bilder mit geschriebenem Manifest
   (Adobe/Firefly automatisch) werden gefunden. Ohne Manifest -> nicht erkennbar.
   Ehrlich benennen.
3. **Resize/Crop bricht die Signatur** (relevant, sobald man Bilder aus einer
   Pipeline zieht): optional die "Original-URL" ohne Resize-Querystring pruefen.
   Fuer den generischen PoC nur ein Feature, kein Kernproblem.

---

## Detection-Technik

- **Bevorzugt:** offizielle `c2pa`-Python-Lib (`Reader`, liest Manifest +
  Assertions; Rust-Wheel). Hinter Zscaler mit uv-TLS-Setup
  (UV_NATIVE_TLS=1, SSL_CERT_FILE leeren) installieren.
- **Fallback:** `c2patool`-Binary (CLI, stabile JSON-Ausgabe), falls die Lib
  hinter dem Proxy zickt.
- Nie JUMBF von Hand parsen.
- **Phase-0-Test (zuerst!):** installiert die Lib hinter dem Proxy? Liest sie
  `digitalSourceType` aus einem signierten Testbild? -> entscheidet Lib vs. Binary.

---

## Architektur (Clean Architecture, python-specialist-Template)

```
src/c2pa_scanner/
  domain/models.py       ImageFinding, C2paVerdict (dataclass/pydantic)
  domain/protocols.py    C2paReader-Protocol
  services/scan_service.py   orchestriert: Bilder sammeln -> lesen -> klassifizieren
  infrastructure/c2pa_reader.py   c2pa-Lib-Adapter (implementiert Protocol)
  infrastructure/image_source.py  lokaler Ordner + optional URL-Download (httpx)
  __main__.py            CLI zuerst (argparse: ordner/urls), spaeter Textual-App
  app.py / app.tcss      Textual-UI (DataTable links, Bildvorschau rechts)
```

Wiederverwendung aus console-error-scanner (spaeter, fuer die TUI):
Bildvorschau-Panel (TGP/Sixel + Halfblock), paralleler Scan (Semaphore),
Timer-Fortschritt, Themes, CrashGuard, LogPanel, Settings.

---

## Phasen

### Phase 0 - Engine + Proxy-Beweis (CLI, zuerst)
- pyproject + minimales Package, `c2pa`-Lib als Dependency.
- `C2paReader`-Adapter: Manifest lesen, `digitalSourceType` extrahieren.
- CLI: `c2pa-scanner <ordner>` -> Tabelle (Datei | C2PA? | digitalSourceType |
  Verdict) auf stdout.
- Gegen ein selbst signiertes Testbild verifizieren (die Lib bringt Test-Certs
  mit) + gegen ein echtes Adobe/Firefly-Bild, falls vorhanden.
- **Ergebnis:** Lib installiert hinter Proxy? Lesen ok? -> Lib vs. c2patool.

### Phase 1 - Textual-TUI
Engine in die UI wickeln: DataTable + Bildvorschau rechts, paralleler Scan,
Ordner-/URL-Auswahl, Export (CSV/JSON), Themes/About/Settings.

### Phase 2 - Optional
URL-Download + "Original ohne Resize"-Pruefung; Batch ueber viele Quellen.

---

## Entscheidungen (getroffen)

- **Projektform:** eigenes, **privates** GitHub-Repo `c2pa-scanner`.
- **Kein Sitefinity, kein Seiten-Crawl** in diesem Repo (das ist Story 2, .NET).
- **Reihenfolge:** Engine/CLI zuerst, dann TUI.

## Offen

- `c2pa`-Lib vs. `c2patool`-Binary (Phase 0 entscheidet).
- Lizenz: Apache-2.0 (Standard).
