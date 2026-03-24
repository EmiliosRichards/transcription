# External Data Map (Postgres) — Dialfire

This document captures what the app reads from the external Postgres (Dialfire) and how to reproduce the same results in DBeaver/psql. Sourced from your latest inspection (steps 0–5). We’ll append steps 6–9 once available.

## 0) Connection metadata

Server confirms we’re on the right host and timezone:

```
server_ip: 185.216.75.247
db: dialfire
schema: public
pg_version: PostgreSQL 13.22 (Debian 13.22-0+deb11u1)
timezone: Asia/Nicosia
```

## 1) Inventory: views and matviews

Views present in `public` (used by the app):

```
agent_data
agent_latest_last_2_months
campaign_agent_reference_data
campaign_state_reference_data
```

Materialized views in `public`:

```
none
```

## 2) Locate objects by key columns

Objects containing multiple key columns used by the app:

```
public.agent_data
public.campaign_agent_reference_data
```

## 3) View definitions (authoritative)

### public.agent_data

Purpose: Denormalized call rows from `transactions` → `connections` → `recordings` → `contacts`. Filtered to `t.fired IS NOT NULL`. Used throughout for call lists, statistics, and grouping. The app de-duplicates per `transaction_id` ordering by `recordings_started` and `connections_duration`.

```1:40:docs/data-map-reference.md
-- public.agent_data source

CREATE OR REPLACE VIEW public.agent_data
AS SELECT to_char(
        CASE
            WHEN t.fired::text ~ '^\d{4}-\d{2}-\d{2}'::text THEN t.fired::date
            ELSE NULL::date
        END::timestamp with time zone, 'YYYY-MM-DD'::text) AS transactions_fired_date,
    to_char(r.started::timestamp without time zone, 'HH24:MI'::text) AS recordings_start_time,
    c.duration AS connections_duration,
    t."user_loginName" AS transactions_user_login,
    t.status AS transactions_status,
    t.status_detail AS transactions_status_detail,
    t.pause_time_sec AS transactions_pause_time_sec,
    t.edit_time_sec AS transactions_edit_time_sec,
    t.wrapup_time_sec AS transactions_wrapup_time_sec,
    t.wait_time_sec AS transactions_wait_time_sec,
    r.started AS recordings_started,
    r.stopped AS recordings_stopped,
    r.location AS recordings_location,
    c.phone AS connections_phone,
    co."$id" AS contacts_id,
    co."$campaign_id" AS contacts_campaign_id,
    co.firma AS contacts_firma,
    co.notiz AS contacts_notiz,
    concat_ws(' '::text, co."Geprüfte_Anrede", co."AP_Vorname", co."AP_Nachname") AS contacts_full_name,
    t.id AS transaction_id
   FROM transactions t
     LEFT JOIN connections c ON c.transaction_id::text = t.id::text
     LEFT JOIN recordings r ON r.connection_id::text = c.id::text
     LEFT JOIN contacts co ON co."$id"::text = r.contact_id::text
  WHERE t.fired IS NOT NULL;
```

Usage:
- De-duplication pattern in `server/external-db.ts` (`getAgentData`, `getAgentStats`, `getAgentCallDetails`).
- Filters by `transactions_user_login`, `contacts_campaign_id`, and date range using `transactions_fired_date` (text YYYY-MM-DD).

### public.agent_latest_last_2_months

Purpose: Active agents in the last two months with proper-cased login names. Used to populate agent filters.

```
-- public.agent_latest_last_2_months source

CREATE OR REPLACE VIEW public.agent_latest_last_2_months
AS SELECT DISTINCT ON ((lower(t."user_loginName"::text))) initcap(t."user_loginName"::text)::character varying(50) AS transactions_user_login,
    r.started::timestamp without time zone::date AS recordings_date
   FROM transactions t
     JOIN connections c ON c.transaction_id::text = t.id::text
     JOIN recordings r ON r.connection_id::text = c.id::text
  WHERE r.started IS NOT NULL AND r.stopped IS NOT NULL AND r.started::timestamp without time zone >= (CURRENT_DATE - '2 mons'::interval) AND t."user_loginName"::text !~* '^[0-9a-f]{32}$'::text
  ORDER BY (lower(t."user_loginName"::text)), (r.started::timestamp without time zone) DESC, t."user_loginName";
```

Usage:
- Loaded by `server/external-db.ts#getUniqueAgents()` and deduplicated case-insensitively.

### public.campaign_agent_reference_data

Purpose: Reference of which agents have activity per campaign. Filters out likely hash-only user names.

```
-- public.campaign_agent_reference_data source

CREATE OR REPLACE VIEW public.campaign_agent_reference_data
AS SELECT DISTINCT agent_data.contacts_campaign_id,
    agent_data.transactions_user_login
   FROM agent_data
  WHERE length(agent_data.transactions_user_login::text) <> 32
  ORDER BY agent_data.contacts_campaign_id;
```

Usage:
- Queried by `server/external-db.ts#getCampaignAgentReference()` to populate project filters.

### public.campaign_state_reference_data

Purpose: Reference of possible outcomes per campaign (status + status_detail).

```
-- public.campaign_state_reference_data source

CREATE OR REPLACE VIEW public.campaign_state_reference_data
AS SELECT DISTINCT agent_data.contacts_campaign_id,
    agent_data.transactions_status,
    agent_data.transactions_status_detail
   FROM agent_data
  ORDER BY agent_data.contacts_campaign_id;
```

Usage:
- `server/external-db.ts#getCampaignStateReference()` and `getOutcomeStatus()`; consumed by `/api/campaign-categories/:campaignId?`.

## 4) Base tables: columns, counts, indexes

- Row counts (snapshot):

```
transactions: 3,778,594
connections:  1,462,854
contacts:       813,896
recordings:     887,052
```

- Example columns (abbreviated; see reference for full list):
  - `transactions`: id, contact_id, status, status_detail, fired, wait_time_sec, edit_time_sec, pause_time_sec, wrapup_time_sec, user, …
  - `recordings`: id, contact_id, connection_id, started, stopped, location, …
  - `connections`: id, transaction_id, contact_id, phone, duration, remote_number, line_number, …
  - `contacts`: very wide table with company/contact fields (e.g., firma, vorname, nachname, notiz, various metadata columns)

- Indexes (abbrev.):

```
connections: connections_pkey on (id)
contacts:    contacts_pkey on ("$id"), "$id|$md5" on ("$id","$md5")
recordings:  recordings_pkey on (id)
transactions: transactions_pkey on (id)
```

## 5) Reference data — agents and campaigns

- Agents (from `agent_latest_last_2_months`):

```
Ahmet.Eren
Alena.Acar
Ali.Cam
Alisha.Rzepka
Bahar.Satir
Baris.Aktan
Behiye.Arslan
Buket.Beken
Danilo.Faber
Duygu.Oeksuez
Efsane.Karaman
Emine.Gueler
Emrah.Akgoez
Erik Wewetzer
Esra.Findik
Fadime Demirdogen
Goekcen.Sirin
Gonca.Sapan
Hakan.Gungor1
Huelya.Palali
Ihsan.Simseker
Ilayda.Oezen
Ismail.Bereketoglu
Jeannette.Milde
Kamile.Esiyok
Koecher.Mirijam
Mark.Authried
Meltem.Zeren
Muenevver.Tolu
Murat.Demirdögen
Nicole Seifert1
Nicole.Seifert1
Nicole.Weber
Nurhan.Sakar
Oezkan.Kaplan
Oezlem.Akbas
Rabia.Usta
Sabrina.Asrav
Sebnem.Klink
Sedef.Battal
Selim.Toklu
Songuel.Yurtseven
Temurcin.Tuerer
Tim Langer
Tugce.Karaca
Turgay.Simseker
Vasilios.Kalaitzis
```

- Fallback (raw tables) note: direct `transactions_user_login` was not found on `transactions` in this instance, thus the view is the correct source for agent discovery.

---

## How the app uses these

- Reads agents and campaigns from the views above to populate filters.
- For statistics and call details, it queries `public.agent_data` with parameterized filters (agent login, campaign ID, date window) and applies `DISTINCT ON (transaction_id)` ordering by `recordings_started DESC NULLS LAST, connections_duration DESC` to deduplicate.
- Outcome math in the app:
  - erfolgreich = `transactions_status = 'success'`
  - abgeschlossen = `transactions_status IN ('success','declined')`
  - anzahl = de-duplicated row count
  - time metrics (hours) are derived from sec/ms fields in the view.

Next steps: when you share outputs for steps 6–9, we’ll append examples for de-duplicated calls, outcome distributions, day aggregates, and Cyprus time conversions.


