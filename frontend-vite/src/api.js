// API client for AskNova frontend (Vite version)
const API_BASE_URL = "https://YOUR-BACKEND-RENDER-URL.onrender.com";

// Helper function for JSON fetch
async function fetchJson(url, options = {}) {
  const r = await fetch(url, options);
  const t = await r.text();
  let d = {};
  if (t) {
    try {
      d = JSON.parse(t);
    } catch (e) {
      d = {};
    }
  }
  if (!r.ok) {
    const msg = typeof d.detail === "string" ? d.detail : t || "Erreur";
    throw new Error(msg);
  }
  return d;
}

// API endpoints
export const api = {
  // Conversations
  getConversations: () => fetchJson(`${API_BASE_URL}/conversations`),
  getConversationMessages: (id) => fetchJson(`${API_BASE_URL}/conversations/${encodeURIComponent(id)}/messages`),
  deleteConversation: (id) => fetchJson(`${API_BASE_URL}/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  
  // Datasets
  getDatasets: () => fetchJson(`${API_BASE_URL}/datasets`),
  createDataset: (name) => fetchJson(`${API_BASE_URL}/datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }),
  
  // Dataset operations
  getDatasetIngestStatus: (datasetId) => fetchJson(`${API_BASE_URL}/datasets/${datasetId}/ingest/status`),
  getDatasetFiles: (datasetId) => fetchJson(`${API_BASE_URL}/datasets/${datasetId}/files`),
  autoIngestFile: (datasetId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetchJson(`${API_BASE_URL}/datasets/${datasetId}/ingest/auto`, { method: "POST", body: fd });
  },
  deleteDatasetFile: (datasetId, storedName) => fetchJson(`${API_BASE_URL}/datasets/${datasetId}/files`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stored_name: storedName }),
  }),
  getFilePreview: (datasetId, storedName) => fetchJson(`${API_BASE_URL}/datasets/${datasetId}/files/${encodeURIComponent(storedName)}/preview`),
  getFileRawUrl: (datasetId, storedName) => `${API_BASE_URL}/datasets/${datasetId}/files/${encodeURIComponent(storedName)}/raw`,
  
  // Ask questions
  askDataset: (datasetId, question, mode, provider, model, conversationId, activeFiles) => {
    const body = { question, mode, provider, model, conversation_id: conversationId };
    if (activeFiles !== undefined) body.active_files = activeFiles;
    return fetchJson(`${API_BASE_URL}/datasets/${datasetId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  askFree: (question, provider, model, conversationId) => fetchJson(`${API_BASE_URL}/ask/free`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, provider, model, conversation_id: conversationId }),
  }),
  
  // Configuration
  getLlmOptions: () => fetchJson(`${API_BASE_URL}/llm/options`),
  getLimits: () => fetchJson(`${API_BASE_URL}/limits`),
};
