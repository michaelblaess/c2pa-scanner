# c2pa-scanner

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <a href="README.md">English</a> &middot;
  <img src="docs/flags/de.svg" height="13" alt=""> <b>Deutsch</b>
</p>

---

Erkennt den **C2PA-Herkunftsnachweis** in Bildern und filtert die **KI-generierten**
heraus - damit Du sie nach dem EU AI Act (Art. 50) kennzeichnen kannst.

Es liest den `digitalSourceType` aus einem C2PA-Manifest (z.B. von Adobe / Firefly automatisch
eingebettet) und bewertet jedes Bild: KI-generiert, KI-bearbeitet, andere Herkunft oder keine.

## Wofür dieses Tool gedacht ist - und wofür nicht

> **Dieses Tool prüft Deine eigenen Bilder und Seiten** auf die KI-Kennzeichnung nach dem
> EU AI Act und macht sie rechtssicher - nicht mehr und nicht weniger.
>
> Es ist **ausdrücklich NICHT** dazu gedacht, fremde Webseiten zu durchleuchten, Verstöße zu
> sammeln und daraus Abmahnungen zu basteln. Wer das damit vorhat, ist hier falsch.
>
> Zur Einordnung: Der C2PA-Scan ist nur ein **Indiz** - er findet ausschließlich Bilder mit
> Herkunfts-Manifest (z.B. Adobe / Firefly), niemals alle KI-Bilder. Er ist kein Rechtsgutachten
> und kein Beweis für einen Verstoß. Nutze ihn fair.
>
> **Rechtsgrundlage:** EU AI Act (Verordnung (EU) 2024/1689), insbesondere Artikel 50
> (Transparenzpflichten), gültig ab 2. August 2026.
> Gesetzestext (EUR-Lex): https://eur-lex.europa.eu/eli/reg/2024/1689/oj
> Artikel 50 (lesbar): https://artificialintelligenceact.eu/article/50/

## Verwendung

```bash
# Grafische TUI starten (Standard ohne Befehl)
c2pa-scanner
c2pa-scanner tui https://www.example.com/sitemap.xml

# Sitemap crawlen und alle Bilder auf C2PA-/KI-Herkunft prüfen (auch nur die Domain -
# die Sitemap wird dann automatisch gesucht)
c2pa-scanner scan https://www.example.com/sitemap.xml
c2pa-scanner scan ./sitemap.xml

# Signiertes C2PA-Testbild erzeugen (Positiv-Testfall)
c2pa-scanner make-testimage ./test-ki.jpg
c2pa-scanner make-testimage ./test-bearbeitet.jpg --edited
```

## Wie es funktioniert

Die Erkennung ist mehrstufig und bewusst auf wenige Falsch-Positive ausgelegt:

- **C2PA-Manifest** (Primärsignal): die offizielle `c2pa`-Lib liest das signierte Manifest; die
  `digitalSourceType`-Assertion entscheidet das Verdict (`trainedAlgorithmicMedia` = KI-generiert,
  `compositeWithTrainedAlgorithmicMedia` = KI-bearbeitet).
- **XMP/EXIF-`digitalSourceType`** (Zweitsignal): denselben IPTC-Marker liest das Tool auch aus dem
  XMP, wenn kein gültiges C2PA vorhanden ist - so werden Bilder erkannt, die ihre Signatur beim
  Verkleinern verloren, das XMP aber behalten haben.
- **Erzeugendes Tool** (Fallback): fehlt jeder `digitalSourceType`, wird der `Software`- bzw.
  `CreatorTool`-Tag gegen eine kuratierte Liste eindeutiger Generativ-KI-Tools geprüft (Midjourney,
  DALL-E, Stable Diffusion, Adobe Firefly, ...). Mehrdeutige Editoren wie Photoshop oder GIMP zählen
  bewusst NICHT, um Falsch-Positive zu vermeiden.
- **Seiten-Crawl:** aus einer Sitemap werden alle Seiten geladen und die Bild-URLs per Regex über das
  rohe HTML extrahiert - das findet auch Bilder in Web-Component-Attributen/Shadow-DOM, nicht nur
  klassische `<img src>`. Fehlt eine direkte Sitemap-URL, wird sie automatisch gesucht (robots.txt,
  danach übliche Standardpfade). Eine vollständigere Sitemap als die offizielle liefert das
  Schwester-Tool [Sitemap-Tracker](https://github.com/michaelblaess/sitemap-tracker) - dessen
  XML-Ausgabe lädst Du einfach als lokale Datei.
- **Browser-Rendering** (optional, Standard aus): zuschaltbar rendert das Tool jede Seite zusätzlich in
  einem headless Chromium (Playwright) und ergänzt so Bilder, die erst per JavaScript ins (Shadow-)DOM
  geladen werden - als Union mit der Regex-Extraktion.

**Grenzen:** Bilder ganz ohne Herkunftssignal (kein C2PA, kein XMP/EXIF) sind nicht als KI erkennbar.
Metadaten lassen sich entfernen - Screenshot, erneutes Speichern, und viele Plattformen strippen sie
beim Upload. Ein Treffer ist ein belastbares Indiz **für** KI; das Fehlen ist **kein** Beweis dagegen.
Jedes Verkleinern/Zuschneiden bricht die C2PA-Signatur - also möglichst das Original prüfen.

### In der TUI

- **Live-Bildvorschau** rechts neben der Trefferliste, mit klickbarem Link zur Fundseite und einem
  Dialog für das rohe C2PA-Manifest.
- **Seiten-Vorschau** (optional): unter dem Bild ein Screenshot der gerenderten Fundseite, zum Bild
  gescrollt - so siehst Du ohne Absprung, ob ein KI-Label auf/am Bild dargestellt wird.
- **Filter & Sortierung**, Toggle "Nur KI-Bilder", **Export** per Rechtsklick (JSON, JIRA-Tabelle,
  Klartext) und **Testbild-Signierung** als Positiv-Testfall.

### Andere Erkennungsmethoden - und warum (noch) nicht implementiert

Vollständigkeitshalber die Alternativen, die es gibt, aber bewusst NICHT eingebaut sind:

- **Unsichtbare Wasserzeichen** (Google SynthID, Meta, Amazon Titan): robust gegen Bearbeitung, aber
  jedes Verfahren braucht den Detektor seines Anbieters - es gibt keinen offenen, universellen Reader.
  SynthID ist nur über Googles eigenes Portal prüfbar, nicht als Bibliothek. **Grund: nicht
  integrierbar.**
- **ML-Klassifikatoren** ("ist das KI?", z.B. Hive, Sensity, Illuminarty): generatorübergreifend und
  nach Kompression/Verkleinern unzuverlässig (hohe Falsch-Positiv- UND Falsch-Negativ-Raten), veralten
  schnell, adversarial fragil. **Grund: für eine Kennzeichnungs-Entscheidung nicht verteidigbar** - das
  würde die belastbare Aussage untergraben; höchstens als separat markiertes "unsicheres Indiz" denkbar,
  das das Ergebnis nicht steuert.
- **Forensik/Statistik** (Frequenzspektrum, Rausch-Residuen, Diffusions-Fingerprints): Forschungsgrad,
  kein fertiges Werkzeug, gleiche Zuverlässigkeits-Vorbehalte wie ML-Klassifikatoren. **Grund:
  Aufwand/Nutzen passt nicht.**
- **Fingerprint-/Hash-Abgleich** gegen eine Registry bekannter KI-Bilder: funktioniert nur, wenn das
  Bild dort registriert ist - keine allgemeine Lösung. **Grund: zu geringe Abdeckung.**

Die Leitlinie: lieber wenige, belastbare Signale (Provenienz) als viele unsichere - passend zum Zweck,
eine rechtssichere KI-Kennzeichnung nach EU AI Act Art. 50 zu unterstützen.

## Lizenz

Apache-2.0.
