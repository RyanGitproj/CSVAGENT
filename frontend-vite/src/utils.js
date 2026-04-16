// Utility functions for AskNova frontend (Vite version)

// Generate unique ID
export function newId() {
  return crypto.randomUUID();
}

// Format message time
export function formatMsgTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;
  
  if (diff < 60000) return "à l'instant";
  if (diff < 3600000) return `il y a ${Math.floor(diff / 60000)} min`;
  if (diff < 86400000) return `il y a ${Math.floor(diff / 3600000)} h`;
  if (diff < 604800000) return `il y a ${Math.floor(diff / 86400000)} j`;
  
  return date.toLocaleDateString('fr-FR');
}

// Get file kind icon
export function fileKindIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const iconMap = {
    'csv': '📊',
    'xlsx': '📊',
    'xls': '📊',
    'pdf': '📄',
    'txt': '📝',
    'json': '📋',
    'default': '📁'
  };
  return iconMap[ext] || iconMap.default;
}

// Read stored conversation ID
export function readStoredConversationId() {
  try {
    return localStorage.getItem('current_conversation_id');
  } catch {
    return null;
  }
}

// Store conversation ID
export function storeConversationId(id) {
  try {
    if (id) {
      localStorage.setItem('current_conversation_id', id);
    } else {
      localStorage.removeItem('current_conversation_id');
    }
  } catch {
    // Ignore storage errors
  }
}
