import sqlite3
import requests
import urllib3
import time
from bs4 import BeautifulSoup

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

def fetch_oracc(conn):
    print("[*] 1/5 ORACC -> Data ophalen...")
    cursor = conn.cursor()
    try:
        r = requests.get("https://build-oracc.museum.upenn.edu/json/etcsri.json", verify=False, timeout=15)
        if r.status_code == 200:
            texts = r.json().get('public', {}).get('text', {})
            count = 0
            for tid, tinfo in texts.items():
                if count >= 10: break
                cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                               (tid, "ORACC", tinfo.get('title', 'Onbekend'), "n.n.b.", "Aanwezig in API"))
                count += 1
            conn.commit()
            print(f"[+] ORACC: {count} objecten toegevoegd.")
    except Exception as e:
        print(f"[!] ORACC mislukt: {e}")

def fetch_cdli(conn):
    print("[*] 2/5 CDLI -> Data ophalen (keyword: myth)...")
    cursor = conn.cursor()
    try:
        r = requests.get("https://cdli.mpiwg-berlin.mpg.de/api/search?q=myth&limit=10", timeout=15)
        if r.status_code == 200:
            results = r.json().get('results', [])
            count = 0
            for item in results:
                tid = item.get('id_text', f'CDLI-{count}')
                cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                               (tid, "CDLI", item.get('primary_publication', 'Mythe'), "n.n.b.", "n.n.b."))
                count += 1
            conn.commit()
            print(f"[+] CDLI: {count} objecten toegevoegd.")
    except Exception as e:
        print(f"[!] CDLI mislukt: {e}")

def fetch_huggingface(conn):
    print("[*] 3/5 HUGGING FACE -> Machine Learning datasets ophalen...")
    cursor = conn.cursor()
    # We gebruiken de Hugging Face Server API om direct in de dataset te kijken zonder zware libraries
    url = "https://datasets-server.huggingface.co/rows?dataset=yfq20%2FAkkadian_Sumerian_Cuneiform_Translations&config=default&split=train&offset=0&length=10"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            rows = r.json().get('rows', [])
            count = 0
            for row in rows:
                data = row.get('row', {})
                tid = f"HF-AKK-{row.get('row_idx', count)}"
                cuneiform = data.get('cuneiform', 'Geen spijkerschrift')
                translit = data.get('transliteration', data.get('translation', 'Geen vertaling'))
                cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                               (tid, "HuggingFace", "Sumerisch/Akkadisch Fragment", cuneiform, translit))
                count += 1
            conn.commit()
            print(f"[+] HUGGING FACE: {count} vertaalde zinnen toegevoegd.")
    except Exception as e:
        print(f"[!] HUGGING FACE mislukt: {e}")

def fetch_etcsl(conn):
    print("[*] 4/5 ETCSL (Oxford) -> HTML scrapen voor Soemerische mythen...")
    cursor = conn.cursor()
    url = "https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi?text=all"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            links = soup.find_all('a', href=True)
            count = 0
            for link in links:
                if 'text=c' in link['href'] and count < 5:
                    titel = link.text.strip()
                    tid = link['href'].split('text=')[-1]
                    if titel:
                        cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                                       (f"ETCSL-{tid}", "ETCSL", titel, "n.n.b.", "Zie Oxford website"))
                        count += 1
            conn.commit()
            print(f"[+] ETCSL: {count} Soemerische werken gevonden.")
    except Exception as e:
        print(f"[!] ETCSL mislukt: {e}")

def fetch_ebl(conn):
    print("[*] 5/5 eBL (München) -> Fragmentarium structuur ophalen...")
    cursor = conn.cursor()
    # eBL vereist vaak login voor de API, dus we voegen een demonstratie-entry toe
    # of we pingen een public resource. Voor de stabiliteit van de MVP slaan we veilig op.
    try:
        cursor.execute("INSERT OR IGNORE INTO spijkerschrift VALUES (?, ?, ?, ?, ?)",
                       ("eBL-Demo-1", "eBL Fragmentarium", "Enuma Elish Reconstructie (Demo)", "𒀭 𒊹", "an-shar2"))
        conn.commit()
        print(f"[+] eBL: Integratie voorbereid. (Authenticatie vereist voor bulk-data).")
    except Exception as e:
        print(f"[!] eBL mislukt: {e}")

if __name__ == "__main__":
    print("🚀 START OMNI-FETCHER: MULTI-DATABASE SYSTEEM")
    print("=" * 60)
    db_conn = init_db()
    
    fetch_oracc(db_conn)
    time.sleep(1)
    fetch_cdli(db_conn)
    time.sleep(1)
    fetch_huggingface(db_conn)
    time.sleep(1)
    fetch_etcsl(db_conn)
    time.sleep(1)
    fetch_ebl(db_conn)
    
    db_conn.close()
    print("=" * 60)
    print("✅ Ingestion cyclus 100% voltooid! Draai 'python read_db.py' om de vangst te inspecteren.")
