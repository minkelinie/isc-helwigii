import os
import time
import subprocess

print("🤖 Auto-Runner Actief. Wachten op 'run_me.py' in /data...")

while True:
    if os.path.exists("run_me.py"):
        print("\n🚀 Nieuw script gedetecteerd: run_me.py! Uitvoeren...")
        time.sleep(1) # Korte pauze voor bestandsoverdracht
        
        try:
            result = subprocess.run(["python", "run_me.py"], capture_output=True, text=True)
            print("--- OUTPUT ---")
            print(result.stdout)
            if result.stderr:
                print("--- ERRORS ---")
                print(result.stderr)
        except Exception as e:
            print(f"⚠️ Fout bij uitvoeren: {e}")
            
        # Hernoem het bestand zodat het niet in een oneindige loop raakt
        timestamp = int(time.time())
        os.rename("run_me.py", f"executed_{timestamp}_run_me.py")
        print("✅ Uitvoering voltooid. Wachten op volgende opdracht...")
        
    time.sleep(2)
