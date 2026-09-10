import psycopg
from pgvector.psycopg import register_vector

conn = psycopg.connect(
    "host=localhost port=5433 dbname=vectordb user=postgres password=testpw"
)
register_vector(conn)

with conn.cursor() as cur:
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    print("pgvector:", cur.fetchone()[0])

    cur.execute("DROP TABLE IF EXISTS items")
    cur.execute("CREATE TABLE items (id bigserial PRIMARY KEY, embedding vector(3))")
    cur.execute("INSERT INTO items (embedding) VALUES (%s), (%s)", ([1, 2, 3], [4, 5, 6]))
    cur.execute("SELECT id, embedding FROM items ORDER BY embedding <-> %s LIMIT 5", ([3, 1, 2],))
    print(cur.fetchall())

conn.commit()
conn.close()