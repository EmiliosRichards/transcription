## Example outputs (shape only)

### Evaluator (v2) — `result`
```json
{
  "input_url": "https://example.com",
  "company_name": "Example GmbH",
  "manuav_fit_score": 6.4,
  "confidence": "medium",
  "reasoning": "Beispiel ist grundsätzlich DACH-relevant und hat einen klaren B2B-Wedge, aber zentrale Belege zu Dealgröße und Sales-Motion sind öffentlich nicht eindeutig.",
  "positives": [
    "Klare DACH-Signale (Impressum/Standorte/DE-Ansprache).",
    "Erkennbarer B2B-Wedge mit erreichbaren Buyer-Rollen."
  ],
  "concerns": [
    "Unklar, ob typische Dealgrößen/LTV hoch genug sind, um bezahltes Outbound wirtschaftlich zu tragen.",
    "Unklar, ob es einen dedizierten Vertriebsprozess (Angebote/Rechnung/Rahmenverträge) gibt."
  ],
  "company_size_indicators_text": "…",
  "innovation_level_indicators_text": "…",
  "targets_specific_industry_type": ["…"],
  "is_startup": null,
  "is_ai_software": null,
  "is_innovative_product": null,
  "is_disruptive_product": null,
  "is_vc_funded": null,
  "is_saas_software": null,
  "is_complex_solution": null,
  "is_investment_product": null
}
```

### Sales pitch service (v2) — `/pitch` response
```json
{
  "matched_partner_name": "Some Partner GmbH",
  "sales_pitch": "Wie gesagt, wir haben uns auf Ihrer Webseite angeschaut, was Sie machen...\n\n- ...\n- ...\n- ...\n- Dort generieren wir aktuell etwa 5 Leads pro Tag.\n\nUnd da hat mein Chef mich gebeten, ...",
  "sales_pitch_template": "Wie gesagt, ... {avg_leads_per_day} ...",
  "match_reasoning": [
    "Überschneidung in der callable Zielgruppe: ...",
    "Ähnliche Buying Motion: ..."
  ],
  "avg_leads_per_day": 5
}
```

