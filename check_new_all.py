import csv, hashlib, psycopg2
csv_path = r'data_pipelines\data\sql imports\Dexter_Campaigns_another_but_this_time_with_the_one_off_archived_mappings_SELECT_202508271751.csv'
urls=[]
with open(csv_path, newline='', encoding='utf-8') as f:
    r=csv.DictReader(f)
    for row in r:
        u = row.get('url') or row.get('location')
        if u: urls.append(u)
hashes=[hashlib.sha1(u.encode('utf-8')).hexdigest() for u in urls]
conn=psycopg2.connect('postgresql://postgres:Kii366@localhost:5433/manuav')
cur=conn.cursor()
cur.execute('SELECT url_sha1 FROM media_pipeline.audio_files WHERE url_sha1 = ANY(%s)', (hashes,))
existing=set(x[0] for x in cur.fetchall())
missing=[u for u,h in zip(urls, hashes) if h not in existing]
print('total_csv=', len(urls), 'in_db=', len(urls)-len(missing), 'new=', len(missing))
