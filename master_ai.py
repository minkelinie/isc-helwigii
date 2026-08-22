import sqlite3
import requests
import os
import time

print("🤖 OX-Stealth Master AI Pipeline (Zelfbouw Editie)")
print("=" * 60)

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("[!] Fout: OPENROUTER_API_KEY is niet ingesteld in de terminal!")
    exit()

db_path = "cuneiform_master.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, titel, cuneiform FROM spijkerschrift WHERE cuneiform != 'n.n.b.' LIMIT 5")
rows = c.fetchall()

if not rows:
    print("[!] Geen spijkerschrift gevonden om te verwerken.")
    exit()

# We gebruiken het extreem stabiele Llama 3.1 70B model via OpenRouter
model_engine = "meta-llama/llama-3.1-70b-instruct"
print(f"[*] Model geselecteerd: {model_engine}")
print(f"[*] Aantal te verwerken teksten: {len(rows)}")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

for tid, titel, cuneiform in rows:
    print(f"\n📖 ID: {tid} | {titel}")
    print(f"🏺 Ruw: {cuneiform}")
    
    payload = {
        "model": model_engine,
        "messages": [
            {"role": "system", "content": "You are an expert Assyriologist. Translate the cuneiform signs accurately and concisely."},
            {"role": "user", "content": f"Translate this cuneiform to English: {cuneiform}"}
        ]
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            ai_output = r.json()['choices'][0]['message']['content'].strip()
            print(f"🤖 AI Output: {ai_output}")
            c.execute("UPDATE spijkerschrift SET transliteratie = ? WHERE id = ?", (f"AI: {ai_output}", tid))
        else:
            print(f"⚠️ API Fout {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"⚠️ Netwerk Fout: {e}")
    
    time.sleep(1) # Korte pauze voorkomt API rate-limiting

conn.commit()
conn.close()
print("=" * 60)
print("✅ AI Inference succesvol! Data is opgeslagen in de kluis.")
