import os
from sqlalchemy import create_engine, text

raw = os.environ.get("DATABASE_URL","")
url = raw.strip('"').replace("postgresql+asyncpg","postgresql+psycopg2")
print("URL =", url)

e = create_engine(url)
with e.connect() as c:
    print("db,user =", c.execute(text("select current_database(), current_user")).fetchone())
    has_schema = c.execute(text("select exists(select 1 from information_schema.schemata where schema_name='media_pipeline')")).scalar()
    print("has_media_pipeline =", has_schema)