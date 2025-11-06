import argparse
import csv
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate pitch_templates.csv scaffold from taxonomy_reasons_v1.csv")
    p.add_argument("--run", required=True, help="Run directory path")
    args = p.parse_args()

    run = Path(args.run)
    labels_path = run / "taxonomy" / "taxonomy_reasons_v1.csv"
    outp = run / "taxonomy" / "pitch_templates.csv"

    labels = list(csv.DictReader(open(labels_path, encoding="utf-8")))
    outp.parent.mkdir(parents=True, exist_ok=True)

    with open(outp, "w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=["reason_label_id","reason_label","target","template"])
        w.writeheader()

        examples = {
            "Not interested": {
                "GK": "Alles klar – ich möchte Sie nicht aufhalten. Könnte ich Ihrer Leitung eine kurze, konkrete Übersicht mailen, wie andere Heime {campaign_name} nutzen, und melde mich nur, wenn es relevant ist?",
                "DM": "Verstehe, aktuell kein Thema. Zwei Punkte, warum {campaign_name} später doch spannend war: (1) Dokumentationszeit sinkt typ. um ~30%; (2) kein Systemwechsel nötig. Darf ich Ihnen eine 3-Minuten-Übersicht schicken und in {callback_window} noch mal kurz anrufen?",
            },
            "Decision maker unavailable": {
                "GK": "Danke! Wann ist {dm_role} am besten erreichbar? Ich sende parallel eine kurze Übersicht, damit {dm_role} in 60 Sekunden sieht, worum es geht. Passt {callback_time} für einen Rückruf?",
                "DM": "Danke für den Hinweis – ich schicke vorab eine 1-Seiten-Zusammenfassung. Passt {callback_time} für ein kurzes 10-Minuten-Gespräch nach Ihrer Rückkehr?",
            },
            "Centralized Decisions": {
                "GK": "Verstanden – Entscheidungen liegen bei der Zentrale. Können Sie mir die zentrale Anlaufstelle nennen, oder darf ich Ihnen eine Vorlage schicken, die Sie intern weiterleiten?",
                "DM": "Danke – wenn die Zentrale entscheidet: Ich sende eine knappe Vorlage mit Nutzenpunkten für die Freigabe. Wen nenne ich als Ansprechpartner in der Zentrale, und gibt es ein Zeitfenster für die Prüfung?",
            },
        }

        for r in labels:
            rid, rname = r["reason_label_id"], r["reason_label"]
            for tgt in ("GK", "DM"):
                tpl = examples.get(rname, {}).get(tgt, "")
                w.writerow({
                    "reason_label_id": rid,
                    "reason_label": rname,
                    "target": tgt,
                    "template": tpl,
                })

    print("Wrote:", outp)


if __name__ == "__main__":
    main()


