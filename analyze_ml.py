import sqlite3
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import seaborn as sns
import matplotlib.pyplot as plt

print("🧠 Start ML-Analyse: Cuneiform N-Grams & Similarity")
print("=" * 60)

# 1. Data inladen (alleen de rijen met echt spijkerschrift)
conn = sqlite3.connect("cuneiform_master.db")
df = pd.read_sql_query("SELECT id, titel, cuneiform FROM spijkerschrift WHERE cuneiform != 'n.n.b.'", conn)
conn.close()

if len(df) < 2:
    print("[!] Niet genoeg teksten met ruw spijkerschrift om te vergelijken. (Minimaal 2 nodig).")
    exit()

print(f"[*] {len(df)} teksten ingeladen voor NLP-analyse.")

# 2. AI Feature Extraction (Character N-grams TF-IDF)
# Dit leert patronen van 1 tot 3 opeenvolgende spijkerschrifttekens
vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(1, 3))
tfidf_matrix = vectorizer.fit_transform(df['cuneiform'])

print(f"[*] Het algoritme heeft {len(vectorizer.get_feature_names_out())} unieke teken-patronen geleerd.")

# 3. Wiskundige overlap berekenen (Cosine Similarity)
similarity_matrix = cosine_similarity(tfidf_matrix)

# 4. Visualiseren als Seaborn Heatmap
plt.figure(figsize=(8, 6))
sns.heatmap(similarity_matrix, annot=True, cmap="YlOrRd", 
            xticklabels=df['id'], yticklabels=df['id'], vmin=0, vmax=1)
plt.title("Wiskundige Overlap tussen Spijkerschrift Tabletten")
plt.tight_layout()

# 5. Opslaan
output_img = "heatmap.png"
plt.savefig(output_img, dpi=300)
print("-" * 60)
print(f"✅ ACADEMISCHE CONCLUSIE:")
print(f"   De Cosine Similarity is succesvol berekend over de ruwe cuneiform vectoren.")
print(f"   De heatmap is opgeslagen als '{output_img}'.")
print(f"✅ Open de map 'OxStealthData' op het bureaublad van je Mac om de afbeelding te bekijken!")
