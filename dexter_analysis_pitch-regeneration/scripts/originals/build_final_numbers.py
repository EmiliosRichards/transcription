import os
import csv
from collections import defaultdict, Counter


PHONES_CSV = os.environ.get("PHONES_CSV", r"output\dexter_sampled_phones.csv")
CONTACTS_CSVS = [
    os.environ.get(
        "CONTACTS_CSV_1",
        r"data_pipelines\data\transcription_dexter_analysis\contacts_2025-09-25T13_00_55.137Z.csv",
    ),
    os.environ.get(
        "CONTACTS_CSV_2",
        r"data_pipelines\data\transcription_dexter_analysis\contacts_2025-09-25T13_04_14.995Z.csv",
    ),
]
OUT_OK = os.environ.get("OUT_OK", r"output\\dexter_final_numbers.csv")
OUT_OK_CONTACTS_FMT = os.environ.get(
    "OUT_OK_CONTACTS_FMT", r"output\\dexter_final_numbers_contacts_fmt.csv"
)
OUT_EXCLUDED = os.environ.get("OUT_EXCLUDED", r"output\\dexter_final_excluded.csv")
OUT_REPORT = os.environ.get("OUT_REPORT", r"output\\dexter_final_report.txt")

# Supported country codes for normalization (DE/CH/AT)
CCS = ("49", "41", "43")


def digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def variants(num_digits: str) -> set[str]:
    """Return a set of plausible variants for matching across formats.

    - Local 0XXXXXXXX → 49XXXXXXXX / 0049XXXXXXXX, similarly for 41/43
    - 49XXXXXXXX → 0XXXXXXXX / 0049XXXXXXXX
    - 0049XXXXXXXX → 49XXXXXXXX / 0XXXXXXXX
    Keeps the original digits as well.
    """
    out: set[str] = {num_digits}
    if num_digits.startswith("0") and len(num_digits) > 1:
        for cc in CCS:
            out.add(cc + num_digits[1:])
            out.add("00" + cc + num_digits[1:])
    for cc in CCS:
        if num_digits.startswith(cc) and len(num_digits) > len(cc):
            rest = num_digits[len(cc) :]
            out.add("0" + rest)
            out.add("00" + cc + rest)
    if num_digits.startswith("00") and len(num_digits) > 2:
        for cc in CCS:
            tag = "00" + cc
            if num_digits.startswith(tag) and len(num_digits) > len(tag):
                rest = num_digits[len(tag) :]
                out.add(cc + rest)
                out.add("0" + rest)
    return out


def read_contacts(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        sample = f.read(4096)
    delim = "\t" if sample.count("\t") >= sample.count(",") else ","
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter=delim)
        for row in r:
            rows.append(row)
    return rows


def load_sampled_phones(path: str) -> list[tuple[str, str]]:
    phones: list[tuple[str, str]] = []  # (raw, digits)
    with open(path, "r", encoding="utf-8") as f:
        # Try headered CSV first
        try:
            r = csv.DictReader(f)
            fieldnames = [c.strip().lower() for c in (r.fieldnames or [])]
            if "phone" in fieldnames:
                for row in r:
                    raw = (row.get("phone") or next(iter(row.values()), "")).strip()
                    d = digits(raw)
                    if d:
                        phones.append((raw, d))
                return phones
        except Exception:
            pass

    # Fallback to simple first-column CSV
    with open(path, "r", encoding="utf-8") as f2:
        rd = csv.reader(f2)
        first = next(rd, None)
        if first is not None:
            maybe = (first[0] or "").strip()
            if maybe and "phone" not in maybe.lower():
                d = digits(maybe)
                if d:
                    phones.append((maybe, d))
        for row in rd:
            if not row:
                continue
            raw = (row[0] or "").strip()
            d = digits(raw)
            if d:
                phones.append((raw, d))
    return phones


def main() -> None:
    phones = load_sampled_phones(PHONES_CSV)
    if not phones:
        raise SystemExit(f"No phones loaded from {PHONES_CSV}")

    phone_digits_set = {d for _, d in phones}

    # Candidate columns from contacts to search numbers in
    candidates_cols = [
        "$phone",
        "Telefonnummer",
        "Mobiltelefonnummer",
        "Mobile",
        "Direct",
        "HQ",
        "$caller_id",
    ]
    task_key = "$task"
    company_key = "firma"

    # Map our target phone (digits) -> list of (contact_row, raw_phone_from_contacts)
    matches: defaultdict[str, list[tuple[dict, str]]] = defaultdict(list)

    for cpath in CONTACTS_CSVS:
        if not cpath:
            continue
        if not os.path.exists(cpath):
            continue
        for row in read_contacts(cpath):
            # collect raw and digits for each relevant column
            seen_raw_digits: list[tuple[str, str]] = []
            for col in candidates_cols:
                if col in row and row[col]:
                    raw_val = str(row[col]).strip()
                    d = digits(raw_val)
                    if d:
                        seen_raw_digits.append((raw_val, d))
            if not seen_raw_digits:
                continue
            # compute variants per raw and assign
            for raw_val, d in seen_raw_digits:
                vset = variants(d)
                for target in phone_digits_set:
                    if target in vset:
                        matches[target].append((row, raw_val))

    ok_rows: list[dict] = []
    ok_rows_contacts_fmt: list[dict] = []
    excluded_rows: list[dict] = []

    for raw, d in phones:
        pairs = matches.get(d, [])
        if not pairs:
            ok_rows.append({"phone": raw, "company": ""})
            ok_rows_contacts_fmt.append({"phone": raw, "company": ""})
            continue
        stufe_pairs = [
            (r, rv)
            for (r, rv) in pairs
            if (r.get(task_key, "") or "").strip().lower() == "anrufen_stufe"
        ]
        if stufe_pairs:
            comp = ""
            chosen_raw_fmt = None
            for (r, rv) in stufe_pairs:
                nm = (r.get(company_key) or "").strip()
                if nm:
                    comp = nm
                if not chosen_raw_fmt and rv:
                    chosen_raw_fmt = rv
            ok_rows.append({"phone": raw, "company": comp})
            ok_rows_contacts_fmt.append({"phone": (chosen_raw_fmt or raw), "company": comp})
        else:
            comp = ""
            for (r, _rv) in pairs:
                nm = (r.get(company_key) or "").strip()
                if nm:
                    comp = nm
                    break
            excluded_rows.append(
                {
                    "phone": raw,
                    "company": comp,
                    "reason": "matched_but_task_not_anrufen_stufe",
                }
            )

    os.makedirs(os.path.dirname(OUT_OK) or ".", exist_ok=True)
    with open(OUT_OK, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phone", "company"])
        w.writeheader()
        w.writerows(ok_rows)

    # Contacts-formatted output
    with open(OUT_OK_CONTACTS_FMT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phone", "company"])
        w.writeheader()
        w.writerows(ok_rows_contacts_fmt)

    with open(OUT_EXCLUDED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["phone", "company", "reason"])
        w.writeheader()
        w.writerows(excluded_rows)

    total = len(phones)
    incl = len(ok_rows)
    excl = len(excluded_rows)
    msg = [
        f"Total sampled numbers: {total}",
        f"Included (pass): {incl}",
        f"Excluded (matched but wrong task): {excl}",
        f"Outputs:",
        f"  - {OUT_OK}",
        f"  - {OUT_OK_CONTACTS_FMT}",
        f"  - {OUT_EXCLUDED}",
    ]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(msg))
    print("\n".join(msg))


if __name__ == "__main__":
    main()


