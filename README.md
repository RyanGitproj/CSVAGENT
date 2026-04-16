# AskNova — Analyse de données par IA

Importez des fichiers CSV/Excel ou des documents PDF et posez des questions en langage naturel. Obtenez des réponses précises grâce à une approche SQL-first pour les données tabulaires et à une recherche sémantique (RAG) pour les documents.

## Vue d'ensemble

AskNova est une application full-stack qui permet de:
- **Analyser des données tabulaires** (CSV/Excel) avec une approche SQL-first pour des résultats fiables et vérifiables
- **Rechercher des documents** (PDF) avec une recherche sémantique et RAG avec citations
- **Poser des questions** en langage naturel et obtenir des réponses précises
- **Supporter plusieurs providers LLM** (Groq, Gemini, Ollama)

Idéal pour les boutiques, restaurants et entreprises qui ont besoin d'analyser rapidement leur inventaire, catalogues, menus ou fiches produits.

## Stack Technique

**Backend:**
- FastAPI (Python)
- LangChain pour l'intégration LLM
- FAISS pour la recherche vectorielle
- DuckDB pour les requêtes SQL

**Frontend:**
- React
- Vite (outil de build)
- Interface moderne et responsive

## Structure du Projet

```
csv_repo-main/
├── app/                    # Backend FastAPI
│   ├── config.py          # Configuration
│   ├── server.py          # Serveur API
│   ├── embeddings.py      # Providers d'embeddings
│   ├── llm.py             # Providers LLM
│   ├── rate_limit.py      # Rate limiting
│   └── services/          # Logique métier
├── frontend-vite/          # Frontend React + Vite
│   ├── src/
│   │   ├── App.jsx       # Composant React principal
│   │   ├── main.jsx      # Point d'entrée
│   │   ├── api.js        # Client API
│   │   ├── utils.js      # Utilitaires
│   │   └── css/          # Styles
│   ├── public/assets/    # Assets statiques
│   └── dist/             # Build de production
├── tests/                  # Tests backend
├── requirements.txt        # Dépendances Python
└── .gitignore             # Règles Git ignore
```

## Lancer Localement

### Backend

```bash
# Activer l'environnement virtuel
.venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Démarrer le backend
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Backend fonctionne sur: http://localhost:8000
Documentation API: http://localhost:8000/docs

### Frontend

```bash
cd frontend-vite

# Installer les dépendances
npm install

# Démarrer le serveur de développement
npm run dev
```

Frontend fonctionne sur: http://localhost:5173

## Variables d'Environnement

Créez un fichier `.env` à la racine du projet:

```env
# Provider LLM (groq, gemini, ollama)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Ollama (si vous utilisez des modèles locaux)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Gemini (alternative)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

# Embeddings
EMBEDDINGS_PROVIDER=sentence_transformers
EMBEDDINGS_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Frontend (dans frontend-vite/.env)
VITE_API_URL=http://localhost:8000
```

## Déploiement

Le projet est conçu pour être déployé avec le backend et le frontend séparés.

### Backend

Déployez le backend sur n'importe quel service d'hébergement Python (Heroku, Railway, etc.):

- Configurez les variables d'environnement requises
- Commande de démarrage: `uvicorn app.server:app --host 0.0.0.0 --port $PORT`

### Frontend

Déployez le frontend sur n'importe quel service d'hébergement statique (Netlify, Surge, etc.):

- Configurez la variable d'environnement `VITE_API_URL` avec l'URL de votre backend
- Commande de build: `npm run build`
- Répertoire de sortie: `dist/`

## Notes

- **Frontend et backend séparés** - déployés indépendamment
- **Communication API via HTTP** - CORS configuré pour la production
- **Docker NON utilisé** - déploiement via services d'hébergement standard
- **Rate limiting** - configuré pour la protection de l'API
- **Providers LLM multiples** - Groq (rapide, tier gratuit), Gemini, Ollama (local)

## Endpoints API

- `GET /health` - Vérification de santé
- `GET /limits` - Limites et quotas actuels
- `GET /llm/options` - Providers et modèles LLM disponibles
- `POST /datasets` - Créer un dataset
- `GET /datasets` - Lister tous les datasets
- `POST /datasets/{id}/ingest/auto` - Ingestion automatique (PDF ou CSV/Excel)
- `POST /datasets/{id}/ask` - Poser une question sur un dataset
- `POST /ask/free` - Chat libre sans dataset
- `GET /conversations` - Lister les conversations
- `GET /conversations/{id}/messages` - Messages d'une conversation
- `DELETE /conversations/{id}` - Supprimer une conversation

## Licence

Copyright © 2026 Tsioritiana Ryan
