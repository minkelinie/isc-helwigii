import sqlite3
import pandas as pd

print("\n🔍 INHOUD VAN DE KLUIS (cuneiform_master.db)")
print("=" * 60)

db_path = "cuneiform_master.db"

try:
    conn = sqlite3.connect(db_path)
    
    # We gebruiken pandas omdat het automatisch mooie tabellen print in de terminal
    query = "SELECT id, bron, titel, cuneiform FROM spijkerschrift LIMIT 10"
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("De database is nog leeg. Voer eerst de scraper uit!")
    else:
        # Dit zorgt ervoor dat pandas kolommen mooi uitlijnt in de terminal
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.max_colwidth', 30)
        print(df.to_string(index=False))
        
        # Laat ook het totaal zien
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM spijkerschrift")
        totaal = cursor.fetchone()[0]
        print("-" * 60)
        print(f"📊 Totaal aantal geregistreerde objecten: {totaal}")

except sqlite3.OperationalError:
    print(f"[!] Fout: Kan de database '{db_path}' niet vinden of openen.")
finally:
    if 'conn' in locals():
        conn.close()
