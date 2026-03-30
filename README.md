# AskCSV — posez des questions à vos CSV en langage naturel

Une petite API qui vous évite d’ouvrir Excel pour l’énième fois : vous uploadez un fichier CSV, il est indexé (Parquet + FAISS), puis vous conversez avec un agent LangChain qui interroge vos données via du pandas exécuté dans un bac à sable sécurisé.

En résumé : **téléversement → indexation → questions-réponses en français ou en anglais**, le tout derrière une API FastAPI documentée.

---

## Ce dont vous avez besoin

- **Python 3.11+**
- **[Poetry](https://python-poetry.org/)** pour les dépendances
- Une **clé API OpenAI** (les embeddings et le modèle de chat passent par OpenAI)

---

## Installation

À la racine du projet :

```bash
poetry install
```

Copiez le fichier d’exemple des variables d’environnement et renseignez vos vraies valeurs **dans un fichier local qui ne partira jamais sur Git** :

```bash
copy .env.example .env
```

Sur macOS/Linux :

```bash
cp .env.example .env
```

Ouvrez `.env` et complétez au minimum `OPENAI_API_KEY=`. Le reste (LangSmith, modèles, température) est optionnel — voyez les commentaires dans `.env.example`.

---

## Lancer l’API en local

```bash
poetry run uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
```

Ensuite ouvrez votre navigateur sur **http://localhost:8000** — vous serez redirigé vers la doc interactive (**Swagger**). C’est souvent le plus simple pour tester l’upload et les questions.

Endpoints utiles :

- `GET /health` — vérifie que le service répond
- `POST /parquet/upload_file` — envoi d’un CSV (multipart)
- `POST /askcsv/double/{process_id}` — conversation sur les données liées à un `process_id` (celui retourné après l’upload)

---

## LangSmith (facultatif)

Si vous voulez **tracer et déboguer** les chaînes LangChain, créez un compte sur [LangSmith](https://smith.langchain.com/), puis dans votre `.env` :

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=votre_clé
LANGCHAIN_PROJECT=nom_du_projet
```

Si vous n’en avez pas besoin, laissez le traçage désactivé — l’API fonctionne très bien sans.

---

## Avec Docker

Construction de l’image :

```bash
docker build -t askcsv-api .
```

Lancement (pensez à passer votre clé OpenAI, sans la commiter dans un fichier d’image) :

```bash
docker run -e OPENAI_API_KEY=%OPENAI_API_KEY% -p 8080:8080 askcsv-api
```

Sous PowerShell, `%OPENAI_API_KEY%` fait référence à la variable d’environnement déjà définie sur votre machine. Sous bash :

```bash
docker run -e OPENAI_API_KEY="$OPENAI_API_KEY" -p 8080:8080 askcsv-api
```

L’API écoute alors sur le **port 8080** du conteneur.

---

## Tests

```bash
poetry run pytest
```

---
