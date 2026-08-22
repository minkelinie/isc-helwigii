import sqlite3
import requests
import urllib3
import time

urllib3.disable_warnings()

def init_db(db_path="cuneiform_master.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
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
    return conn

def fetch_oracc(conn, limit=10):
    print("[*] ORACC -> Data ophalen...")
    cursor = conn.cursor()
    try:
        r = requests.get("https://build-oracc.museum.upenn.edu/json/etcsri.json", verify=False, timeout=15)
        if r.status_code == 200:
            texts = r.json().get('public', {}).get('text', {})
            count = 0
            for tid, tinfo in texts.items():
                if count >= limit: break
                cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                               (tid, "ORACC", tinfo.get('title', 'Zonder titel'), "n.n.b.", "Aanwezig in structuur"))
                count += 1
            conn.commit()
            print(f"[+] ORACC -> {count} nieuwe objecten toegevoegd.")
        else:
            print(f"[!] ORACC -> Fout: HTTP {r.status_code}")
    except Exception as e:
        print(f"[!] ORACC -> Verbinding mislukt: {e}")

def fetch_cdli_search(conn, keyword="myth", limit=5):
    print(f"[*] CDLI -> Zoeken op keyword '{keyword}'...")
    cursor = conn.cursor()
    url = f"https://cdli.mpiwg-berlin.mpg.de/api/search?q={keyword}&limit={limit}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            results = r.json().get('results', [])
            count = 0
            for item in results:
                # 'id_text' is de beroemde CDLI P-number (bijv. P123456)
                tid = item.get('id_text', 'ONBEKEND')
                titel = item.get('primary_publication', 'Mythe')
                cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                               (tid, "CDLI", titel, "Moet via OCR/Akkademia", "n.n.b."))
                count += 1
            conn.commit()
            print(f"[+] CDLI -> {count} objecten gevonden en toegevoegd.")
        else:
            print(f"[!] CDLI -> Fout: HTTP {r.status_code}. (Mogelijk veranderd API format)")
    except Exception as e:
        print(f"[!] CDLI -> Verbinding mislukt: {e}")

if __name__ == "__main__":
    print("🚀 Start Federated Data Fetcher")
    print("=" * 50)
    
    # Koppel de database
    db_conn = init_db()
    
    # Voer de scrapers uit
    fetch_oracc(db_conn, limit=10)
    time.sleep(1) # Even pauze tussen requests
    fetch_cdli_search(db_conn, keyword="myth", limit=10)
    
    db_conn.close()
    print("=" * 50)
    print("✅ Ingestion cyclus voltooid! Draai 'python read_db.py' om de data te bekijken.")
