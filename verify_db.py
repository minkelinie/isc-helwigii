import sqlite3
conn = sqlite3.connect("/data/cuneiform_master.db")
cur = conn.cursor()

cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name LIKE "%myth%" OR name LIKE "%phylo%" OR name LIKE "%motif%"')
print("Tables:", [r[0] for r in cur.fetchall()])

cur.execute('SELECT COUNT(*) FROM myth_texts')
print("Myth texts:", cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM motif_taxonomy')
print("Motif taxonomy:", cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM motif_instances')
print("Motif instances:", cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM motif_distances')
print("Motif distances:", cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM phylo_tree')
print("Phylo tree nodes:", cur.fetchone()[0])

cur.execute('SELECT COUNT(*) FROM motif_migrations')
print("Motif migrations:", cur.fetchone()[0])

# Show sample tree
cur.execute('SELECT node_id, label, period, node_type, bootstrap_support FROM phylo_tree ORDER BY node_type DESC, distance_from_root LIMIT 20')
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1][:40]:40s} | {r[2]:12s} | {r[3]:10s} | boot={r[4]:.1f}')

conn.close()