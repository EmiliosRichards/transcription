import csv, hashlib, psycopg2, requests
csv_path = r'data_pipelines\data\sql imports\Dexter_Campaigns_another_but_this_time_with_the_one_off_archived_mappings_SELECT_202508271751.csv'
urls=[]
with open(csv_path, newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        u=row.get('url') or row.get('location')
        if u: urls.append(u)
hashes=[hashlib.sha1(u.encode('utf-8')).hexdigest() for u in urls]
conn=psycopg2.connect('postgresql://postgres:Kii366@localhost:5433/manuav')
cur=conn.cursor()
cur.execute('SELECT url_sha1 FROM media_pipeline.audio_files WHERE url_sha1 = ANY(%s)', (hashes,))
existing=set(x[0] for x in cur.fetchall())
missing=[u for u,h in zip(urls,hashes) if h not in existing]
live=[]
for u in missing:
    try:
        r=requests.head(u, timeout=(3,5), allow_redirects=True)
        if r.status_code==404: continue
        live.append(u)
        if len(live)>=50: break
    except Exception: pass
print('first_50_live_candidates=', len(live))
for u in live[:10]: print(u)
