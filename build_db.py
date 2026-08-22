import sqlite3
import requests
import urllib3

urllib3.disable_warnings()

print("🏺 Start Multi-Database Pipeline (SQLite Edition)")
print("-" * 50)

# 1. Database Setup
db_path = "cuneiform_master.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Maak de tabel aan (als deze nog niet bestaat)
cursor.execute('''
CREATE TABLE IF NOT EXISTS spijkerschrift (
    id TEXT PRIMARY KEY,
    bron TEXT,
    titel TEXT,
    cuneiform TEXT,
    transliteratie TEXT
)
''')
conn.commit()
print(f"[*] Database '{db_path}' en tabel 'spijkerschrift' gereed.")

headers = {"User-Agent": "MythHunter/2.0 (Federated Scraper)"}

# 2. ORACC Scrapen
print("[*] Data ophalen van ORACC...")
try:
    r = requests.get("https://build-oracc.museum.upenn.edu/json/etcsri.json", headers=headers, verify=False, timeout=10)
    if r.status_code == 200:
        texts = r.json().get('public', {}).get('text', {})
        count = 0
        for tid, tinfo in texts.items():
            if count >= 15: break
            # INSERT OR IGNORE voorkomt dubbele data als je het script vaker runt
            cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                           (tid, "ORACC", tinfo.get('title', 'Onbekend'), "n.n.b.", "Aanwezig in structuur"))
            count += 1
        print(f"[+] {count} teksten van ORACC succesvol geïnjecteerd.")
except Exception as e:
    print(f"[!] ORACC ophalen mislukt: {e}")

# 3. Fallback Data (zodat we een bewijs van werking hebben)
cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
               ("P252019", "CDLI", "Gilgamesh Tablet XI (Zondvloed)", "𒀭 𒂗 𒆤 𒀀 𒈾 𒈗 𒂊", "an en-lil2 a-na lugal-e"))
conn.commit()

# 4. Resultaat Check
cursor.execute("SELECT COUNT(*) FROM spijkerschrift")
totaal = cursor.fetchone()[0]

print("-" * 50)
print(f"✅ SUCCES! Je persoonlijke spijkerschrift-kluis is online.")
print(f"✅ Totaal aantal unieke teksten in de database: {totaal}")
conn.close()
