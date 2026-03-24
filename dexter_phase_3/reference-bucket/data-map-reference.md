Perfect. Run these in order and paste results. We’ll turn them into a “data map” doc.

### 0) Connection metadata
```sql

SELECT inet_server_addr() AS server_ip,
       current_database() AS db,
       current_schema()   AS schema,
       version()          AS pg_version,
       current_setting('TimeZone') AS timezone;

```

185.216.75.247	dialfire	public	PostgreSQL 13.22 (Debian 13.22-0+deb11u1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 10.2.1-6) 10.2.1 20210110, 64-bit	Asia/Nicosia

### 1) Inventory: views and matviews
```sql

-- All views in public
SELECT viewname FROM pg_views WHERE schemaname='public' ORDER BY 1;

agent_data
agent_latest_last_2_months
campaign_agent_reference_data
campaign_state_reference_data

-- Expected views (if present)
SELECT schemaname, viewname
FROM pg_views
WHERE schemaname='public'
  AND viewname IN ('agent_data','campaign_agent_reference_data','campaign_state_reference_data','agent_latest_last_2_months')
ORDER BY viewname;

public	agent_data
public	agent_latest_last_2_months
public	campaign_agent_reference_data
public	campaign_state_reference_data

-- Materialized views in public
SELECT schemaname, matviewname FROM pg_matviews WHERE schemaname='public' ORDER BY 2;

empty

```

### 2) Find objects by key columns (helps if names differ)
```sql

SELECT table_schema, table_name
FROM information_schema.columns
WHERE table_schema='public'
  AND column_name IN ('transactions_user_login','contacts_campaign_id','transactions_fired_date')
GROUP BY table_schema, table_name
HAVING COUNT(*) >= 2
ORDER BY table_schema, table_name;

public	agent_data
public	campaign_agent_reference_data
```

### 3) View definitions (run for any that exist)
```sql

SELECT pg_get_viewdef('public.agent_data'::regclass, true);
SELECT pg_get_viewdef('public.campaign_agent_reference_data'::regclass, true);
SELECT pg_get_viewdef('public.campaign_state_reference_data'::regclass, true);
SELECT definition FROM pg_matviews WHERE matviewname='agent_latest_last_2_months';

result:
 SELECT DISTINCT agent_data.contacts_campaign_id,
    agent_data.transactions_status,
    agent_data.transactions_status_detail
   FROM agent_data
  ORDER BY agent_data.contacts_campaign_id;

```

### 4) Base tables: columns, counts, indexes
```sql

-- Columns
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('transactions','recordings','connections','contacts')
ORDER BY table_name, ordinal_position;

connections	id	character varying
connections	parent_connection_id	character varying
connections	transfer_target_address	character varying
connections	call_uuid	character varying
connections	global_call_uuid	character varying
connections	transaction_id	character varying
connections	task_id	character varying
connections	contact_id	character varying
connections	phone	character varying
connections	user	character varying
connections	actor	character varying
connections	hangup_party	character varying
connections	isThirdPartyConnection	character varying
connections	dialerdomain	character varying
connections	fired	character varying
connections	started	character varying
connections	initiated	character varying
connections	connected	character varying
connections	disconnected	character varying
connections	ended	character varying
connections	duration	numeric
connections	remote_number	character varying
connections	line_number	character varying
connections	technology	character varying
connections	result	character varying
connections	code	numeric
connections	call_initiated	character varying
connections	call_connected	character varying
connections	call_disconnected	character varying
connections	$changed	character varying
contacts	$id	character varying
contacts	$md5	character varying
contacts	$ref	character varying
contacts	$version	character varying
contacts	$campaign_id	character varying
contacts	$task_id	character varying
contacts	$task	character varying
contacts	$status	character varying
contacts	$status_detail	character varying
contacts	$created_date	character varying
contacts	$entry_date	character varying
contacts	$owner	character varying
contacts	$follow_up_date	character varying
contacts	$phone	character varying
contacts	$timezone	character varying
contacts	$caller_id	character varying
contacts	$source	character varying
contacts	$comment	text
contacts	$error	character varying
contacts	$recording	character varying
contacts	$recording_url	character varying
contacts	$changed	character varying
contacts	$$anrufen_task	character varying
contacts	$$anrufen_user	character varying
contacts	$$anrufen_date	character varying
contacts	$$anrufen_status	character varying
contacts	$$anrufen_status_detail	character varying
contacts	Telefonnummer	text
contacts	ansprache	text
contacts	Titel	text
contacts	vorname	text
contacts	nachname	text
contacts	firma	text
contacts	strasse	text
contacts	adresszusatz	text
contacts	plz	text
contacts	ort	text
contacts	email	text
contacts	url	text
contacts	info_1	text
contacts	info_2	text
contacts	info_3	text
contacts	info_4	text
contacts	info_5	text
contacts	HOT_LEAD	text
contacts	notiz	text
contacts	Wiedervorlagenart	text
contacts	Geprüfte_Email	text
contacts	Geprüfte_Anrede	text
contacts	AP_Vorname	text
contacts	AP_Nachname	text
contacts	AP_Funktion	text
contacts	Datum_bei_Termin	text
contacts	Mobiltelefonnummer	text
contacts	Job_Title	text
contacts	Mobile	text
contacts	Direct	text
contacts	HQ	text
contacts	Fax	text
contacts	EBINR	text
contacts	MITARBEITERKLASSE_TEXT	text
contacts	BRANCHE_TEXT	text
contacts	Anzahlbetten	text
contacts	Fachabteilungen	text
contacts	cc	text
contacts	Fachabteilungen_1	text
contacts	Leitung_1	text
contacts	www	text
contacts	A	text
contacts	Anrufen	text
contacts	Geburtsjahr	text
contacts	Anzahl_Allgemeinmediziner	text
contacts	Company_Name_for_Emails	text
contacts	___Employees	text
contacts	Industry	text
contacts	Company_Street	text
contacts	Company_City	text
contacts	Company_State	text
contacts	Company_Country	text
contacts	Company_Postal_Code	text
contacts	Apollo_Account_Id	text
contacts	AP2___Vorname	text
contacts	AP2_Nachname	text
contacts	AP3_Vorname	text
contacts	AP3_Nachname	text
contacts	Persönliche_E_Mail	text
contacts	telefax	text
contacts	transfer_nummer	text
contacts	Geprufte_Anrede	text
contacts	ergebnisfeld_1	text
contacts	ergebnisfeld_2	text
contacts	ergebnisfeld_3	text
contacts	ergebnisfeld_4	text
contacts	ergebnisfeld_5	text
contacts	Phone_number	text
contacts	datenid	text
contacts	firma2	text
contacts	firma3	text
contacts	anrede	text
contacts	titel	text
contacts	position	text
contacts	briefanrede	text
contacts	lkz	text
contacts	land	text
contacts	bundesland	text
contacts	regierungsbezirk	text
contacts	landkreis	text
contacts	branchen	text
contacts	einwohner	text
contacts	geo_breite	text
contacts	geo_laenge	text
contacts	mitarbeiter	text
contacts	No	text
contacts	inter_tel	text
contacts	homepage	text
contacts	Gesprochen_mit_	text
contacts	Wer_ruft_an_	text
contacts	stationär	text
contacts	ambulant	text
contacts	Tel__Nr_1	text
contacts	Gesprochen_mit	text
contacts	Number_Type	text
contacts	Description	text
contacts	Number_Found_At	text
contacts	Short_Description	text
contacts	is_mechanical	text
contacts	is_mechanical_reason	text
contacts	is_mechanical_industry	text
contacts	Company_Address	text
contacts	Mitarbeiterklassifizierung	text
contacts	Zusatz	text
contacts	Branchen	text
contacts	Aufzeichnung_gesendet_AP	text
contacts	Aufzeichnung_gesendet_GK	text
contacts	Ort_2	text
contacts	adressID	text
contacts	Kategorie	text
contacts	Branche	text
contacts	KID	text
contacts	E_Mail	text
contacts	Notizen	text
contacts	AP_Email	text
contacts	AP_Anrede	text
contacts	Datum	text
contacts	Status	text
contacts	Ergebnis	text
contacts	Datum_Termin	text
contacts	Aufnahme_Call	text
contacts	Agent	text
contacts	Datum_Termin_	text
contacts	Record_Id	text
contacts	geprüfte_Email	text
contacts	geprüfte_Anrede	text
contacts	No__of_Employees	text
contacts	Steuerberater	text
contacts	Wirtschaftsprüfer	text
contacts	Rechtsanwälte	text
contacts	Fragezeichen_1	text
contacts	Fragezeichen_2	text
contacts	Fragezeichen_3	text
contacts	Link	text
contacts	Kommentar	text
contacts	_Number	text
contacts	City_Number	text
contacts	Website	text
contacts	Impressum	text
contacts	Country	text
contacts	Mitarbeiter	text
contacts	Hierarchie	text
contacts	Kontaktstandort__Land_	text
contacts	Mitarbeiterzahl	text
contacts	Branche__Unterkategorie_	text
contacts	Land	text
contacts	Ländercode	text
contacts	Termin_Durchgeführt_von	text
contacts	Ansprechpartner	text
contacts	Deal___Titel	text
contacts	Deal___Label	text
contacts	Deal_erstellt	text
contacts	Nummer	text
contacts	Account_Stage	text
contacts	Company_Linkedin_Url	text
contacts	Facebook_Url	text
contacts	Twitter_Url	text
contacts	Keywords	text
contacts	Technologies	text
contacts	Total_Funding	text
contacts	Latest_Funding	text
contacts	Latest_Funding_Amount	text
contacts	Last_Raised_At	text
contacts	Annual_Revenue	text
contacts	Number_of_Retail_Locations	text
contacts	SIC_Codes	text
contacts	Founded_Year	text
contacts	Logo_Url	text
contacts	Subsidiary_of	text
contacts	Primary_Intent_Topic	text
contacts	Primary_Intent_Score	text
contacts	Secondary_Intent_Topic	text
contacts	Secondary_Intent_Score	text
contacts	Mitglieds_Nr___HGK	text
contacts	GVS_Partner	text
contacts	Telefax	text
contacts	Adm_HGK	text
contacts	Fachabteilungen_2	text
contacts	Leitung_2	text
contacts	Satdt	text
contacts	Tel	text
contacts	Leitung	text
contacts	Pflegedienst	text
contacts	Infos_zum_Gespräch	text
contacts	Datum_import	text
contacts	daten_export	text
contacts	Termin_Uhrzeit	text
contacts	Fachabteilungen_3	text
contacts	Leitung_3	text
contacts	Fachabteilungen_4	text
contacts	Leitung_4	text
contacts	Fachabteilungen_5	text
contacts	Leitung_5	text
contacts	Fachabteilungen_6	text
contacts	Leitung_6	text
contacts	Fachabteilungen_7	text
contacts	Leitung_7	text
contacts	Fachabteilungen_8	text
contacts	Leitung_8	text
contacts	Fachabteilungen_9	text
contacts	Leitung_9	text
contacts	Fachabteilungen_10	text
contacts	Leitung_10	text
contacts	Fachabteilungen_11	text
contacts	Leitung_11	text
contacts	Fachabteilungen_12	text
contacts	Leitung_12	text
contacts	Fachabteilungen_13	text
contacts	Leitung_13	text
contacts	Fachabteilungen_14	text
contacts	Leitung_14	text
contacts	Fachabteilungen_15	text
contacts	Leitung_15	text
contacts	Fachabteilungen_16	text
contacts	Leitung_16	text
contacts	Fachabteilungen_17	text
contacts	Leitung_17	text
contacts	Fachabteilungen_18	text
contacts	Leitung_18	text
contacts	Fachabteilungen_19	text
contacts	Leitung_19	text
contacts	Fachabteilungen_20	text
contacts	Leitung_20	text
contacts	Fachabteilungen_21	text
contacts	Leitung_21	text
contacts	Fachabteilungen_22	text
contacts	Leitung_22	text
contacts	Fachabteilungen_23	text
contacts	Leitung_23	text
contacts	Fachabteilungen_24	text
contacts	Leitung_24	text
contacts	Fachabteilungen_25	text
contacts	Leitung_25	text
contacts	Fachabteilungen_26	text
contacts	Leitung_26	text
contacts	Fachabteilungen_27	text
contacts	Leitung_27	text
contacts	Fachabteilungen_28	text
contacts	Leitung_28	text
contacts	Fachabteilungen_29	text
contacts	Leitung_29	text
contacts	Fachabteilungen_30	text
contacts	Leitung_30	text
contacts	Fachabteilungen_31	text
contacts	Leitung_31	text
contacts	Fachabteilungen_32	text
contacts	Leitung_32	text
contacts	Fachabteilungen_33	text
contacts	Leitung_33	text
contacts	Fachabteilungen_34	text
contacts	Leitung_34	text
contacts	Fachabteilungen_35	text
contacts	Leitung_35	text
contacts	Fachabteilungen_36	text
contacts	Leitung_36	text
contacts	Fachabteilungen_37	text
contacts	Leitung_37	text
contacts	Fachabteilungen_38	text
contacts	Leitung_38	text
contacts	Fachabteilungen_39	text
contacts	Leitung_39	text
contacts	Fachabteilungen_40	text
contacts	Leitung_40	text
contacts	Fachabteilungen_41	text
contacts	Leitung_41	text
contacts	Fachabteilungen_42	text
contacts	Leitung_42	text
contacts	Fachabteilungen_43	text
contacts	Leitung_43	text
contacts	Fachabteilungen_44	text
contacts	Leitung_44	text
contacts	Fachabteilungen_45	text
contacts	Leitung_45	text
contacts	Fachabteilungen_46	text
contacts	Leitung_46	text
contacts	Fachabteilungen_47	text
contacts	Leitung_47	text
contacts	Fachabteilungen_48	text
contacts	Leitung_48	text
contacts	Fachabteilungen_49	text
contacts	Leitung_49	text
contacts	Fachabteilungen_50	text
contacts	Leitung_50	text
contacts	Fachabteilungen_51	text
contacts	Leitung_51	text
contacts	Fachabteilungen_52	text
contacts	Leitung_52	text
contacts	Fachabteilungen_53	text
contacts	Leitung_53	text
contacts	Fachabteilungen_54	text
contacts	Leitung_54	text
contacts	Fachabteilungen_55	text
contacts	Leitung_55	text
contacts	Fachabteilungen_56	text
contacts	Leitung_56	text
contacts	Fachabteilungen_57	text
contacts	Leitung_57	text
contacts	Fachabteilungen_58	text
contacts	Leitung_58	text
contacts	Fachabteilungen_59	text
contacts	Leitung_59	text
contacts	Fachabteilungen_60	text
contacts	Leitung_60	text
contacts	Fachabteilungen_61	text
contacts	Leitung_61	text
contacts	Fachabteilungen_62	text
contacts	Leitung_62	text
contacts	Fachabteilungen_63	text
contacts	Leitung_63	text
contacts	Fachabteilungen_64	text
contacts	Leitung_64	text
contacts	Fachabteilungen_65	text
contacts	Leitung_65	text
contacts	Fachabteilungen_66	text
contacts	Leitung_66	text
contacts	Fachabteilungen_67	text
contacts	Leitung_67	text
contacts	Fachabteilungen_68	text
contacts	Leitung_68	text
contacts	Fachabteilungen_69	text
contacts	Leitung_69	text
contacts	Abteilung	text
contacts	Bettenanzahl	text
contacts	CB_Rank__Company_	text
contacts	Headquarters_Location	text
contacts	Operating_Status	text
contacts	Company_Type	text
contacts	Full_Description	text
contacts	Number_of_Employees	text
contacts	Industries	text
contacts	Zielgruppe	text
contacts	ZG_Größe	text
contacts	Old_id	text
contacts	campaign_id	text
contacts	LinkedIn_URL	text
contacts	Ziegruppe	text
contacts	Contact_Telefonnummer	text
contacts	Kaltakquise	text
contacts	Sales_Pitch	text
contacts	Beschreibung	text
contacts	Key_Resonating_Themes	text
contacts	Matched_Partner_Name	text
contacts	Matched_Partner_Description	text
contacts	is_b2b	text
contacts	serves_1000	text
contacts	matched_golden_partner	text
contacts	match_reasoning	text
contacts	Avg_Leads_Per_Day	text
contacts	Rank	text
contacts	Spalte1	text
contacts	Bezeichnung	text
contacts	Entfernung_km_	text
contacts	Krankenhaus	text
contacts	FachAbteilung	text
contacts	Person___Label	text
contacts	Person___E_Mail_Adresse___Privat	text
contacts	Person___E_Mail_Adresse___Sonstiger	text
contacts	Person___Telefon___Privat	text
contacts	Person___Telefon___Mobil	text
contacts	Person___Telefon___Sonstiger	text
contacts	KHM53K6GGECUBTLV	text
contacts	JUZT8N9UBU2LHP8H	text
contacts	export_negative	text
contacts	open	text
contacts	_2024_05_22T07_46_00_975Z	text
contacts	_2024_05_22T07_48_46_273Z	text
contacts	_492661939677	text
contacts	Europe_Berlin	text
contacts	import_2024_05_22_07_45	text
contacts	_02661_93_96_77	text
contacts	anrufen_stufe	text
contacts	_2024_05_22T07_48_46_268Z	text
contacts	failed	text
contacts	BZ_Unternehmen	text
contacts	BZ_Adresse	text
contacts	BZ_Telefonnummer	text
contacts	DB_SVG_Schlüssel	text
contacts	KD_Nummer	text
contacts	G_Branche	text
contacts	is_hochbau	text
contacts	hochbau_confidence	text
contacts	hochbau_evidence	text
contacts	Branche__WZ_	text
contacts	PhoneDetails	text
contacts	HR_Amtsgericht	text
contacts	Register_ID	text
contacts	North_Data_URL	text
contacts	Rechtsform	text
contacts	USt__Id_	text
contacts	Ges__Vertreter_1	text
contacts	Ges__Vertreter_2	text
contacts	Ges__Vertreter_3	text
contacts	Finanzkennzahlen_Datum	text
contacts	Stamm__Grundkapital_EUR	text
contacts	Bilanzsumme_EUR	text
contacts	Gewinn_EUR	text
contacts	Gewinn_CAGR__	text
contacts	Umsatz_EUR	text
contacts	Umsatz_CAGR__	text
contacts	Umsatzrendite__	text
contacts	Eigenkapital_EUR	text
contacts	EK_Quote__	text
contacts	EK_Rendite__	text
contacts	Umsatz_pro_Mitarbeiter_EUR	text
contacts	Steuern_EUR	text
contacts	Steuer_Quote__	text
contacts	Kassenbestand_EUR	text
contacts	Forderungen_EUR	text
contacts	Verbindlichkeiten_EUR	text
contacts	Materialaufwand_EUR	text
contacts	Personalaufwand_EUR	text
contacts	Personalaufwand_pro_Mitarbeiter_EUR	text
contacts	Pensionsrückstellungen_EUR	text
contacts	Immobilien_und_Grundstücke_EUR	text
contacts	Mktg_Tech_Bezugszeitraum	text
contacts	Anzahl_Förderungen_pro_Jahr	text
contacts	Gesamtfördersumme_pro_Jahr_EUR	text
contacts	Patente_pro_Jahr	text
contacts	Marken_pro_Jahr	text
contacts	Address	text
contacts	City	text
contacts	Zip	text
contacts	Lead_Source_Detail	text
contacts	Lead_Source	text
contacts	ICP_Fit	text
contacts	Prio	text
contacts	ICP_Text	text
contacts	Last_Contact_Manuav	text
contacts	Project_Name	text
contacts	Project_Start	text
contacts	Project_Details	text
contacts	KI_Simple_Project_Name	text
contacts	Simple_Project_Details	text
contacts	Company	text
contacts	Phone	text
contacts	Street	text
contacts	Zip_Code	text
contacts	jobtitle	text
contacts	Seniority	text
contacts	Departments	text
contacts	Contact_Owner	text
contacts	Stage	text
contacts	State	text
contacts	Apollo_Contact_Id	text
contacts	First_Name	text
contacts	Last_Name	text
contacts	Title	text
contacts	Lists	text
contacts	Last_Contacted	text
contacts	Account_Owner	text
contacts	Email_Status	text
contacts	Primary_Email_Source	text
contacts	Company_Phone	text
contacts	Letzte_Kontaktaufnahme	text
contacts	Notiz	text
contacts	Datensatz_ID	text
contacts	__Aktualisiert_von_Benutzer__ID	text
contacts	__Erstellt_von_Benutzer__ID	text
contacts	Zeitpunkt	text
contacts	Priorität	text
contacts	Begründung	text
contacts	Firmenprofil_ausführlicher	text
contacts	Company_Alias	text
contacts	Email_Confidence	text
contacts	Work_Direct_Phone	text
contacts	Home_Phone	text
contacts	Mobile_Phone	text
contacts	Other_Phone	text
contacts	Person_Linkedin_Url	text
contacts	SEO_Description	text
contacts	Email_Sent	text
contacts	Email_Open	text
contacts	Email_Bounced	text
contacts	Replied	text
contacts	Demoed	text
contacts	Secondary_Email	text
contacts	Secondary_Email_Source	text
contacts	Tertiary_Email	text
contacts	Tertiary_Email_Source	text
contacts	Company_Name	text
contacts	Office	text
contacts	cid_aid	text
contacts	Branche_pitch	text
contacts	Lead_Pitch	text
contacts	categoryName	text
contacts	ID	text
contacts	Kontakt	text
contacts	Letzer_Kontakt	text
contacts	Gender	text
contacts	Column1	text
contacts	Company_E_mail	text
contacts	Postcode	text
contacts	Town	text
contacts	Deal_ID	text
contacts	Kontakt_ID	text
contacts	Adresse2	text
contacts	Bundesland	text
contacts	id	text
contacts	customer_target_segments	text
contacts	Deal_Name	text
contacts	Kurzbezeichnung	text
contacts	Datensatz_ID___Company	text
contacts	picture	text
contacts	linkedinUrl	text
contacts	timezone	text
contacts	companyDomain	text
contacts	emailStatus	text
contacts	icebreaker	text
contacts	Greetings	text
contacts	lastState	text
contacts	status	text
contacts	_id	text
contacts	Lead_Status__Manuav_	text
contacts	Kommentar__Manuav_	text
contacts	Lead_ID	text
contacts	Business_Model	text
contacts	AP1_Job	text
contacts	AP1___TEL2	text
contacts	AP1___TEL3	text
contacts	AP1___TEL4	text
contacts	AP1___TEL5	text
contacts	AP1___TEL6	text
contacts	AP2___Anrede	text
contacts	AP2___Nachname	text
contacts	AP2___Job	text
contacts	AP2___Email	text
contacts	AP2___TEL1	text
contacts	AP2___TEL2	text
contacts	AP2___TEL3	text
contacts	AP2___TEL4	text
contacts	AP2___TEL5	text
contacts	AP3___Anrede	text
contacts	AP3___Vorname	text
contacts	AP3___Nachname	text
contacts	AP3___Job	text
contacts	AP3___Email	text
contacts	AP3___TEL1	text
contacts	AP3___TEL2	text
contacts	AP3___TEL3	text
contacts	AP4___Anrede	text
contacts	AP4___Vorname	text
contacts	AP4___Nachname	text
contacts	AP4___Job	text
contacts	AP4___Email	text
contacts	AP4___TEL1	text
contacts	AP4___TEL2	text
contacts	AP4___TEL3	text
contacts	AP1___ID	text
contacts	AP2___ID	text
contacts	AP3___ID	text
contacts	AP4___ID	text
contacts	AP1___Anrede_2	text
contacts	AP1___Vorname_2	text
contacts	AP1___Nachname_2	text
contacts	AP1___ID_2	text
contacts	AP1___Job_2	text
contacts	AP1___Email_2	text
contacts	AP1___TEL1_2	text
contacts	AP1___TEL2_2	text
contacts	AP1___TEL3_2	text
contacts	AP1___TEL4_2	text
contacts	AP1___TEL5_2	text
contacts	AP1___TEL6_2	text
contacts	Gegenstand	text
contacts	customer_request	text
contacts	Position	text
contacts	Industrie	text
contacts	Abteilungen	text
contacts	Geschäftsführer	text
contacts	System	text
contacts	gefundene_Firmenbezeichnung_	text
contacts	Gefundener_Firmenname	text
contacts	gefundene_Firmenbezeichnung	text
contacts	AP1_Position	text
contacts	Original_Number	text
contacts	AP2_Vorname	text
contacts	AP2_Position	text
contacts	AP2_TEL1	text
contacts	Originalnummer	text
contacts	Zugeordneter__Golden_Partner_	text
contacts	Ø_Leads_pro_Tag	text
contacts	Vertriebspartner	text
contacts	Leadquelle	text
contacts	Rolle	text
contacts	Eintrag_ID	text
contacts	Lead_Name	text
contacts	Webseite	text
contacts	Zweite_E_Mail	text
contacts	Mobil	text
contacts	Bundesland___Region	text
contacts	Anzahl_Mitarbeiter	text
contacts	Anzahl_Patienten	text
recordings	id	character varying
recordings	contact_id	character varying
recordings	connection_id	character varying
recordings	started	character varying
recordings	stopped	character varying
recordings	filename	character varying
recordings	location	character varying
recordings	$changed	character varying
transactions	id	character varying
transactions	contact_id	character varying
transactions	task_id	character varying
transactions	task	character varying
transactions	status	character varying
transactions	status_detail	character varying
transactions	fired	character varying
transactions	pause_time_sec	numeric
transactions	edit_time_sec	numeric
transactions	wrapup_time_sec	numeric
transactions	wait_time_sec	numeric
transactions	user	character varying
transactions	user_loginName	character varying
transactions	user_branch	character varying
transactions	user_tenantAlias	character varying
transactions	actor	character varying
transactions	type	character varying
transactions	result	character varying
transactions	trigger	character varying
transactions	isHI	boolean
transactions	revoked	boolean
transactions	$changed	character varying

-- Row counts
SELECT 'transactions' AS t, COUNT(*) FROM public.transactions
UNION ALL SELECT 'recordings', COUNT(*) FROM public.recordings
UNION ALL SELECT 'connections', COUNT(*) FROM public.connections
UNION ALL SELECT 'contacts', COUNT(*)    FROM public.contacts;

transactions	3778594
connections	1462854
contacts	813896
recordings	887052

-- Indexes
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND tablename IN ('transactions','recordings','connections','contacts')
ORDER BY tablename, indexname;

connections	connections_pkey	CREATE UNIQUE INDEX connections_pkey ON public.connections USING btree (id)
contacts	$id|$md5	CREATE INDEX "$id|$md5" ON public.contacts USING btree ("$id", "$md5")
contacts	contacts_pkey	CREATE UNIQUE INDEX contacts_pkey ON public.contacts USING btree ("$id")
recordings	recordings_pkey	CREATE UNIQUE INDEX recordings_pkey ON public.recordings USING btree (id)
transactions	transactions_pkey	CREATE UNIQUE INDEX transactions_pkey ON public.transactions USING btree (id)

```

### 5) Agents and campaigns (reference data)
```sql

-- Agents (preferred from view if exists)
SELECT DISTINCT transactions_user_login
FROM public.agent_latest_last_2_months
ORDER BY transactions_user_login
LIMIT 100;

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

-- Fallback: from transactions last 60 days
SELECT DISTINCT t.transactions_user_login
FROM public.transactions t
WHERE t.transactions_user_login IS NOT NULL AND t.transactions_user_login <> ''
  AND t.transactions_fired_date >= (CURRENT_DATE - INTERVAL '60 days')
ORDER BY 1
LIMIT 100;

SQL Error [42703]: ERROR: column t.transactions_user_login does not exist
  Position: 62

-- Campaigns for one agent (replace :agent)
SELECT DISTINCT contacts_campaign_id
FROM public.campaign_agent_reference_data
WHERE transactions_user_login = :agent
ORDER BY 1
LIMIT 100;

-- Fallback: join connections + transactions
SELECT DISTINCT c.contacts_campaign_id
FROM public.connections c
JOIN public.transactions t ON t.transaction_id = c.transaction_id
WHERE t.transactions_user_login = :agent
ORDER BY 1
LIMIT 100;

```

### 6) Core app-like queries (replace placeholders)
Set these once for copy/paste:
- :agent → e.g. 'Ihsan.Simseker'
- :campaign → e.g. '3F767KEPW4V73JZS'
- :from → '2025-08-01'
- :to → '2025-09-05'

```sql

-- 6a) De-duplicated raw calls (matches app DISTINCT ON rule)
SELECT DISTINCT ON (transaction_id) *
FROM public.agent_data
WHERE transactions_user_login = :agent
  AND contacts_campaign_id    = :campaign
  AND transactions_fired_date BETWEEN :from AND :to
ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
LIMIT 10000;

-- 6b) Totals sanity: physical vs distinct transactions
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT transaction_id) AS distinct_transactions
FROM public.agent_data
WHERE transactions_user_login = :agent
  AND contacts_campaign_id    = :campaign
  AND transactions_fired_date BETWEEN :from AND :to;

-- 6c) Outcome distribution (what UI shows)
WITH d AS (
  SELECT DISTINCT ON (transaction_id) *
  FROM public.agent_data
  WHERE transactions_user_login = :agent
    AND contacts_campaign_id    = :campaign
    AND transactions_fired_date BETWEEN :from AND :to
  ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
)
SELECT transactions_status, transactions_status_detail, COUNT(*) AS cnt
FROM d
GROUP BY transactions_status, transactions_status_detail
ORDER BY cnt DESC, transactions_status, transactions_status_detail;

-- 6d) Day-level aggregates (AgentStatistics math)
WITH d AS (
  SELECT DISTINCT ON (transaction_id)
    transaction_id, transactions_status, transactions_status_detail,
    transactions_fired_date::date AS day,
    connections_duration,               -- ms
    transactions_wait_time_sec,         -- s
    transactions_edit_time_sec,         -- s
    transactions_pause_time_sec         -- s
  FROM public.agent_data
  WHERE transactions_user_login = :agent
    AND contacts_campaign_id    = :campaign
    AND transactions_fired_date BETWEEN :from AND :to
  ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
)
SELECT
  day AS date,
  COUNT(*) AS anzahl,
  SUM(CASE WHEN transactions_status='success' THEN 1 ELSE 0 END) AS erfolgreich,
  SUM(CASE WHEN transactions_status IN ('success','declined') THEN 1 ELSE 0 END) AS abgeschlossen,
  SUM(COALESCE(transactions_wait_time_sec,0))/3600.0          AS wartezeit,
  SUM(COALESCE(connections_duration,0))/1000.0/3600.0         AS gespraechszeit,
  SUM(COALESCE(transactions_edit_time_sec,0))/3600.0          AS nachbearbeitungszeit,
  SUM(COALESCE(transactions_pause_time_sec,0))/3600.0         AS vorbereitungszeit,
  SUM(COALESCE(transactions_wait_time_sec,0))/3600.0
  + SUM(COALESCE(connections_duration,0))/1000.0/3600.0
  + SUM(COALESCE(transactions_edit_time_sec,0))/3600.0
  + SUM(COALESCE(transactions_pause_time_sec,0))/3600.0       AS arbeitszeit
FROM d
GROUP BY day
ORDER BY date;

```

### 7) Time zone sanity (UTC → Cyprus)
First check type:
```sql

SELECT data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='agent_data' AND column_name='recordings_started';

```

Then use the appropriate variant:
```sql

-- If recordings_started is text
SELECT transaction_id,
       recordings_started::timestamp AS utc_ts,
       (recordings_started::timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Nicosia') AS cyprus_ts,
       to_char((recordings_started::timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Nicosia'),'HH24:MI') AS cyprus_hhmm
FROM public.agent_data
WHERE transactions_user_login=:agent AND contacts_campaign_id=:campaign AND transactions_fired_date=:from
ORDER BY recordings_started::timestamp DESC NULLS LAST
LIMIT 30;

-- If it is timestamptz (already UTC)
SELECT transaction_id,
       recordings_started AS utc_ts,
       (recordings_started AT TIME ZONE 'Europe/Nicosia') AS cyprus_ts,
       to_char((recordings_started AT TIME ZONE 'Europe/Nicosia'),'HH24:MI') AS cyprus_hhmm
FROM public.agent_data
WHERE transactions_user_login=:agent AND contacts_campaign_id=:campaign AND transactions_fired_date=:from
ORDER BY recordings_started DESC NULLS LAST
LIMIT 30;

```

### 8) Unknown statuses/outcomes (helps spot data issues)
```sql

WITH d AS (
  SELECT DISTINCT ON (transaction_id)
    transactions_status, transactions_status_detail
  FROM public.agent_data
  WHERE transactions_fired_date BETWEEN :from AND :to
  ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
)
SELECT transactions_status, transactions_status_detail, COUNT(*) AS cnt
FROM d
GROUP BY transactions_status, transactions_status_detail
ORDER BY cnt DESC;

```

### 9) Optional: group key preview (matches app grouping)
```sql

WITH d AS (
  SELECT DISTINCT ON (transaction_id) *
  FROM public.agent_data
  WHERE transactions_user_login = :agent
    AND contacts_campaign_id    = :campaign
    AND transactions_fired_date BETWEEN :from AND :to
  ORDER BY transaction_id, recordings_started DESC NULLS LAST, connections_duration DESC NULLS LAST
)
SELECT
  md5(coalesce(contacts_id,'') || '|' || coalesce(contacts_campaign_id,'') || '|' || to_char(transactions_fired_date::date,'YYYY-MM-DD')) AS group_id,
  COUNT(*) AS calls_in_group
FROM d
GROUP BY 1
ORDER BY calls_in_group DESC, group_id
LIMIT 50;

```

Paste the outputs. Then I’ll consolidate them into a `docs/data-map.md` with explanations and direct links back to our code paths.



Ive provided a file called @data-map-reference.md  this contains all the queries and results, please make a file docs/data-map.md using the reference file.