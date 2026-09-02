// Core area: Briefings — the archive of daily editions, each a frozen copy of
// that day's dashboard brief, plus the per-edition screening log.
export const dict: Record<string, string> = {
  Briefings: 'Briefings',
  Briefing: 'Briefing',
  'Daily briefings': 'Tägliche Briefings',
  '{screened} screened → {included} included → {inBriefing} in the briefing':
    '{screened} gesichtet → {included} aufgenommen → {inBriefing} im Briefing',
  'In brief': 'In Kürze',
  'Briefing history': 'Briefing-Verlauf',
  // "Auto-Brief" would read as "automatic letter" — Briefing stays the loanword.
  'auto-brief': 'Auto-Briefing',
  'Screening log →': 'Screening-Protokoll →',
  'Nothing was screened out in this run.': 'In diesem Lauf wurde nichts aussortiert.',
  'No completed runs yet.': 'Noch keine abgeschlossenen Läufe.',
  'Once a pipeline run completes in this workspace, its briefing appears here.':
    'Sobald ein Pipeline-Lauf in diesem Arbeitsbereich abschließt, erscheint sein Briefing hier.',
  'Open briefing →': 'Briefing öffnen →',
  'Search briefings by subject, summary, or paper…':
    'Briefings nach Betreff, Zusammenfassung oder Paper durchsuchen…',
  'Search the digest archive': 'Das Digest-Archiv durchsuchen',
  '{n} of {total} briefings': '{n} von {total} Briefings',
  'No briefings match your search.': 'Keine Briefings entsprechen Ihrer Suche.',
  'Screening log': 'Screening-Protokoll',
  'passed every gate': 'alle Stufen bestanden',
  '1 paper': '1 Paper',
  '{n} papers': '{n} Papers',
  'Screened out': 'Aussortiert',
  'a sample from the log': 'Auszug aus dem Protokoll',
  Paper: 'Paper',
  Source: 'Quelle',
  'Why it did not pass': 'Warum es nicht bestanden hat',
  'The full screening log is retained for the current run; this edition keeps its funnel only.':
    'Das vollständige Screening-Protokoll wird nur für den aktuellen Lauf vorgehalten; diese Ausgabe behält nur ihren Funnel.',
  // Edition titles + summaries (fixtures in src/data/briefings.ts).
  'Dependable agents, durable credentials': 'Verlässliche Agenten, dauerhafte Credentials',
  'Inference that never leaves the enclave': 'Inferenz, die die Enklave nie verlässt',
  'Provenance signed at generation': 'Provenance, signiert bei der Erzeugung',
  'Transformer quality at half the serving cost': 'Transformer-Qualität zu halben Serving-Kosten',
  'The Monday scan: placement and long context': 'Der Montags-Scan: Placement und Long Context',
  'Sealed TEE inference leads the day, cutting the isolation tax from 41% to 9% on long-context workloads — near-native confidential serving for the regulated workloads hybrid cloud has been waiting on. Around it, the agent-reliability line holds: recovery-first tool use, a regenerating benchmark, and curricula that keep compounding.':
    'Versiegelte TEE-Inferenz führt den Tag an und senkt die Isolationskosten bei Long-Context-Workloads von 41% auf 9% — nahezu natives Confidential Serving für die regulierten Workloads, auf die die Hybrid Cloud gewartet hat. Drumherum hält die Agent-Reliability-Linie: Recovery-First-Tool-Use, ein sich regenerierender Benchmark und Curricula, die weiter zulegen.',
  'C2PA credentials signed end-to-end across the generation pipeline, not bolted on afterward — the first of two TrustFabric provenance results this week, and the compliance layer Article 50 assumes.':
    'C2PA-Credentials, Ende-zu-Ende über die Erzeugungs-Pipeline signiert statt nachträglich angeflanscht — das erste von zwei TrustFabric-Provenance-Ergebnissen dieser Woche, und die Compliance-Schicht, die Artikel 50 voraussetzt.',
  'A hybrid state-space model matches transformer quality at roughly half the inference cost — the kind of margin that changes which pilots pencil out on owned hardware.':
    'Ein hybrides State-Space-Modell erreicht Transformer-Qualität bei etwa halben Inferenzkosten — die Art Marge, die verändert, welche Piloten sich auf eigener Hardware rechnen.',
  'Monday runs the wider sweep, and infrastructure leads it: a scheduler that places workloads with data residency as a first-class constraint across hybrid clouds, and a low-risk way to stretch the context windows we already serve — long-context inference without retraining.':
    'Montags läuft der breitere Scan, und die Infrastruktur führt ihn an: ein Scheduler, der Workloads mit Datenresidenz als erstrangiger Randbedingung über Hybrid Clouds platziert, und ein risikoarmer Weg, die Kontextfenster zu strecken, die wir bereits betreiben — Long-Context-Inferenz ohne Retraining.',
}
