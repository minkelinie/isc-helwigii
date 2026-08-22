import requests
import json
import pandas as pd
import os
import urllib3

urllib3.disable_warnings()

print("🏺 Start MYTH HUNTER - CuneiML Editie")
print("-" * 50)

url = "https://zenodo.org/records/10806319/files/CuneiMLv1.2.json"
filename = "CuneiMLv1.2.json"

# 1. DOWNLOAD DE ECHTE DATASET
if not os.path.exists(filename):
    print("[*] Verbinden met academische Zenodo servers...")
    print("[*] Downloaden van de volledige CuneiML dataset (204 MB). Dit duurt even...")
    with requests.get(url, stream=True, verify=False) as r:
        r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print("[+] Download 100% voltooid!")
else:
    print("[+] CuneiML dataset was al lokaal aanwezig.")

# 2. DATA INLADEN EN PARSEN
print("[*] JSON data inladen en spijkerschrift extraheren...")
with open(filename, 'r', encoding='utf-8') as f:
    data = json.load(f)

if isinstance(data, list):
    items = data
elif isinstance(data, dict):
    items = data.get('data', data.get('items', list(data.values())))
else:
    items = []

dataset = []
limit = 50 # We pakken de eerste 50 voor de MVP test
print(f"[*] {len(items)} kleitabletten gevonden in de kluis. We verwerken de eerste {limit}...")

for item in items[:limit]:
    cunei = item.get('cuneiform', item.get('sign', ''))
    if isinstance(cunei, list):
        cunei = " ".join(str(x) for x in cunei)
    if not cunei:
        cunei = str(item)[:200] + "..." # Fallback naar de ruwe structuur
        
    translit = item.get('transliteration', item.get('raw', 'Geen transliteratie'))
    
    dataset.append({
        "ID": item.get('id', 'Onbekend'),
        "Titel/Metadata": item.get('img_url', 'Geen metadata link'),
        "Ruwe_Cuneiform": cunei,
        "Machine_Transliteratie": translit
    })

# 3. CSV AANMAKEN
df = pd.DataFrame(dataset)
output_file = "myth_hunter_database_v1.csv"
df.to_csv(output_file, index=False, encoding='utf-8')

print("-" * 50)
print(f"✅ SUCCES! Bestand '{output_file}' is overschreven met {len(dataset)} échte spijkerschrift objecten.")
print("✅ Bekijk het CSV-bestand op je Mac bureaublad!")
