import sqlite3
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import urllib3
import warnings

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

print("🤖 Start AI-Vertaler (Robuuste PyTorch Engine)")
print("=" * 60)

conn = sqlite3.connect("cuneiform_master.db")
c = conn.cursor()
c.execute("SELECT id, titel, cuneiform FROM spijkerschrift WHERE cuneiform != 'n.n.b.' LIMIT 5")
rows = c.fetchall()

if not rows:
    print("[!] Geen spijkerschrift gevonden.")
    exit()

print("[*] Tokenizer & Neuraal netwerk inladen (Flan-T5)...")
try:
    tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-small")
    model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-small")
    print("[+] Model 'flan-t5-small' succesvol lokaal geladen!")
except Exception as e:
    print(f"[!] Fout bij inladen AI-model: {e}")
    exit()

print("-" * 60)
for r in rows:
    tid, titel, cuneiform = r
    print(f"\n📖 ID: {tid} | {titel}")
    print(f"🏺 Ruw: {cuneiform}")
    try:
        # 1. Tekst omzetten naar tensors (wiskundige vectoren)
        inputs = tokenizer(f"Translate this ancient text: {cuneiform}", return_tensors="pt")
        
        # 2. Het model laten 'nadenken' en genereren
        outputs = model.generate(**inputs, max_length=50)
        
        # 3. Tensors terugvertalen naar leesbare tekst
        out = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        print(f"🤖 AI Output: {out}")
        c.execute("UPDATE spijkerschrift SET transliteratie=? WHERE id=?", (f"AI: {out}", tid))
    except Exception as e:
        print(f"⚠️ Error: {e}")

conn.commit()
conn.close()
print("\n✅ AI Inference cyclus voltooid! Voorspellingen veilig opgeslagen.")
