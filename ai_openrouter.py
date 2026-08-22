import sqlite3
import requests
import os

print("🤖 Start OX-Stealth AI Vertaler (Direct via OpenRouter API)")
print("=" * 60)

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("[!] Fout: OPENROUTER_API_KEY is niet ingesteld in je terminal!")
    exit()

conn = sqlite3.connect("cuneiform_master.db")
c = conn.cursor()
c.execute("SELECT id, titel, cuneiform FROM spijkerschrift WHERE cuneiform != 'n.n.b.' AND cuneiform NOT LIKE '%Zie Oxford%' LIMIT 5")
rows = c.fetchall()

if not rows:
    print("[!] Geen spijkerschrift gevonden om te verwerken.")
    exit()

# We mappen het OX-systeem nu aan een zwaar, academisch capabel model dat wél bestaat op de servers
model_engine = "nvidia/llama-3.1-nemotron-70b-instruct"

print(f"[*] {len(rows)} spijkerschrift-objecten geladen uit cuneiform_master.db.")
print(f"[*] Verbinden met OpenRouter (Engine: {model_engine})...")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/DigitalHumanities",
    "X-Title": "Cuneiform Translator"
}

# 3. AI Inference Loop met kogelvrije error-handling
for row in rows:
    tid, titel, cuneiform = row
    print(f"\n📖 ID: {tid} | {titel}")
    print(f"🏺 Ruw Spijkerschrift: {cuneiform}")
    
    prompt = (
        f"You are a Computational Linguist and Assyriologist. "
        f"Analyze and transliterate/translate this cuneiform text to English: {cuneiform}. "
        f"Keep the output extremely concise and academic."
    )
    
    payload = {
        "model": model_engine,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            # Haal de tekst uiterst voorzichtig op, met een fallback als het model weigert
            ai_output = data.get('choices', [{}])[0].get('message', {}).get('content')
            
            if ai_output: # Controleer of we daadwerkelijk tekst (en geen null) hebben teruggekregen
                ai_output = ai_output.strip()
                print(f"🤖 OX-Stealth Output:\n{ai_output}")
                c.execute("UPDATE spijkerschrift SET transliteratie = ? WHERE id = ?", (f"AI: {ai_output}", tid))
            else:
                print("⚠️ OpenRouter stuurde een leeg (null) bericht terug. Model heeft mogelijk een error.")
        else:
            print(f"⚠️ API Fout (HTTP {r.status_code}): {r.text[:150]}")
    except Exception as e:
        print(f"⚠️ Netwerk of Parsing Fout: {e}")

conn.commit()
conn.close()
print("\n" + "=" * 60)
print("✅ OX-Stealth AI analyse voltooid! De resultaten zijn opgeslagen in cuneiform_master.db.")
