# c2pa-scanner

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <a href="README.md">English</a> &middot;
  <img src="docs/flags/de.svg" height="13" alt=""> <b>Deutsch</b>
</p>

---

Erkennt den **C2PA-Herkunftsnachweis** in Bildern und filtert die **KI-generierten**
heraus - damit du sie nach dem EU AI Act (Art. 50) kennzeichnen kannst.

Es liest den `digitalSourceType` aus einem C2PA-Manifest (z.B. von Adobe / Firefly automatisch
eingebettet) und bewertet jedes Bild: KI-generiert, KI-bearbeitet, andere Herkunft oder keine.

## Wofür dieses Tool gedacht ist - und wofür nicht

> **Dieses Tool prüft deine eigenen Bilder und Seiten** auf die KI-Kennzeichnung nach dem
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
# Ordner (rekursiv) auf C2PA-/KI-Herkunft prüfen
c2pa-scanner scan ./bilder

# Signiertes C2PA-Testbild erzeugen (Positiv-Testfall)
c2pa-scanner make-testimage ./test-ki.jpg
c2pa-scanner make-testimage ./test-bearbeitet.jpg --edited
```

## Wie es funktioniert

- **Erkennung:** die offizielle `c2pa`-Lib liest das Manifest; die `digitalSourceType`-Assertion
  entscheidet das Verdict (`trainedAlgorithmicMedia` / `compositeWithTrainedAlgorithmicMedia` = KI).
- **Grenzen:** Bilder ohne Manifest sind nicht erkennbar. Jedes Resize/Crop bricht die
  C2PA-Signatur - also das Original prüfen, nicht eine verkleinerte Kopie.

## Lizenz

Apache-2.0.
