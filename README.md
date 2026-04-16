# AskNova — AI-Powered Data Analysis

Upload CSV/Excel files or PDF documents and ask questions in natural language. Get accurate answers powered by SQL-first analysis for tabular data and semantic search (RAG) for documents.

## Overview

AskNova is a full-stack application that allows you to:
- **Analyze tabular data** (CSV/Excel) using SQL-first approach for reliable, verifiable results
- **Search documents** (PDF) using semantic search with RAG and citations
- **Ask questions** in natural language and get accurate answers
- **Support multiple LLM providers** (Groq, Gemini, Ollama)

Perfect for shops, restaurants, and businesses that need to quickly analyze their inventory, catalogs, menus, or product sheets.

## Tech Stack

**Backend:**
- FastAPI (Python)
- LangChain for LLM integration
- FAISS for vector search
- DuckDB for SQL queries

**Frontend:**
- React
- Vite (build tool)
- Modern UI with responsive design

## Project Structure

```
csv_repo-main/
├── app/                    # Backend FastAPI
│   ├── config.py          # Configuration
│   ├── server.py          # API server
│   ├── embeddings.py      # Embeddings providers
│   ├── llm.py             # LLM providers
│   ├── rate_limit.py      # Rate limiting
│   └── services/          # Business logic
├── frontend-vite/          # Frontend React + Vite
│   ├── src/
│   │   ├── App.jsx       # Main React component
│   │   ├── main.jsx      # Entry point
│   │   ├── api.js        # API client
│   │   ├── utils.js      # Utilities
│   │   └── css/          # Styles
│   ├── public/assets/    # Static assets
│   └── dist/             # Production build
├── tests/                  # Backend tests
├── requirements.txt        # Python dependencies
└── .gitignore             # Git ignore rules
```

## Run Locally

### Backend

```bash
# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start backend
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Backend runs on: http://localhost:8000
API Documentation: http://localhost:8000/docs

### Frontend

```bash
cd frontend-vite

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend runs on: http://localhost:5173

## Environment Variables

Create a `.env` file in the root directory:

```env
# LLM Provider (groq, gemini, ollama)
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Ollama (if using local models)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Gemini (alternative)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

# Embeddings
EMBEDDINGS_PROVIDER=sentence_transformers
EMBEDDINGS_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Frontend (in frontend-vite/.env)
VITE_API_URL=http://localhost:8000
```

## Deployment

### Backend (Render)

1. Push code to GitHub
2. Connect Render to your GitHub repository
3. Configure environment variables in Render dashboard
4. Render automatically detects Python and uses `requirements.txt`
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn app.server:app --host 0.0.0.0 --port $PORT`

### Frontend (Vercel)

1. Push code to GitHub
2. Connect Vercel to your GitHub repository
3. Configure `VITE_API_URL` environment variable with your backend URL
4. Vercel automatically detects Vite and uses `vercel.json`
5. Build command: `npm run build`
6. Output directory: `dist/`

## Notes

- **Frontend and backend are separated** - deployed independently
- **API communication via HTTP** - CORS configured for production
- **Docker NOT used** - deployment via Render (backend) and Vercel (frontend)
- **File storage** - ephemeral on Render Free Tier (files deleted after inactivity)
- **Rate limiting** - configured for API protection
- **Multiple LLM providers** - Groq (fast, free tier), Gemini, Ollama (local)

## API Endpoints

- `GET /health` - Health check
- `GET /limits` - Current limits and quotas
- `GET /llm/options` - Available LLM providers and models
- `POST /datasets` - Create a dataset
- `GET /datasets` - List all datasets
- `POST /datasets/{id}/ingest/auto` - Auto ingestion (PDF or CSV/Excel)
- `POST /datasets/{id}/ask` - Ask question about dataset
- `POST /ask/free` - Free chat without dataset
- `GET /conversations` - List conversations
- `GET /conversations/{id}/messages` - Get conversation messages
- `DELETE /conversations/{id}` - Delete conversation

## License

MIT License
