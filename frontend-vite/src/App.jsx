import { useEffect, useId, useMemo, useRef, useState } from 'react';
import React from 'react';
import { api } from './api';
import { fileKindIcon, formatMsgTime, newId, readStoredConversationId } from './utils';
import './css/styles.css';

function SourcesList({ sources }) {
  const [open, setOpen] = useState(false);
  const uid = useId().replace(/:/g, "");
  const panelId = "sources-panel-" + uid;
  const btnId = "sources-btn-" + uid;
  if (!sources || !sources.length) return null;
  return (
    <div className="sources-block">
      <button
        type="button"
        className="sources-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        id={btnId}
      >
        <span className="sources-toggle-label">Sources et vérification</span>
        <Icon name="chevron" size={18} className={"sources-chevron" + (open ? " open" : "")} />
      </button>
      {open ? (
        <div className="sources-panel" id={panelId} role="region" aria-labelledby={btnId}>
          {sources.map((s, j) => {
            if (s.kind === "sql") {
              const rows = s.preview_rows || [];
              const cols = rows.length ? Object.keys(rows[0]) : [];
              return (
                <div key={j}>
                  <pre className="sql-pre">{s.sql}</pre>
                  {rows.length ? (
                    <div className="preview-table-wrap">
                      <table className="preview-table">
                        <thead>
                          <tr>
                            {cols.map((k) => (
                              <th key={k}>{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.slice(0, 25).map((row, ri) => (
                            <tr key={ri}>
                              {cols.map((k) => (
                                <td key={k}>{row[k] != null ? String(row[k]) : ""}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              );
            }
            if (s.kind === "doc") {
              return (
                <div key={j} className="doc-source">
                  <div className="doc-meta">
                    {s.source}
                    {s.page != null ? " · p. " + s.page : ""}
                  </div>
                  <div>{s.excerpt}</div>
                </div>
              );
            }
            return null;
          })}
        </div>
      ) : null}
    </div>
  );
}

function Icon({ name, size = 20, className = "", style, ...rest }) {
  const p = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className: "icon " + className,
    style,
    "aria-hidden": true,
    ...rest,
  };
  switch (name) {
    case "menu":
      return (
        <svg {...p}>
          <line x1="4" y1="6" x2="20" y2="6" />
          <line x1="4" y1="12" x2="20" y2="12" />
          <line x1="4" y1="18" x2="20" y2="18" />
        </svg>
      );
    case "plus":
      return (
        <svg {...p}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case "message":
      return (
        <svg {...p}>
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
      );
    case "trash":
      return (
        <svg {...p}>
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
        </svg>
      );
    case "send":
      return (
        <svg {...p}>
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      );
    case "sparkles":
      return (
        <svg {...p}>
          <path d="M12 3v3M12 18v3M5 6l2 2M17 16l2 2M3 12h3M18 12h3M5 18l2-2M17 6l2-2" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      );
    case "database":
      return (
        <svg {...p}>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
          <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
        </svg>
      );
    case "file":
      return (
        <svg {...p}>
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      );
    case "refresh":
      return (
        <svg {...p}>
          <path d="M23 4v6h-6" />
          <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
        </svg>
      );
    case "upload":
      return (
        <svg {...p}>
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
      );
    case "check":
      return (
        <svg {...p}>
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );
    case "x":
      return (
        <svg {...p}>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      );
    case "eye":
      return (
        <svg {...p}>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "chevron":
      return (
        <svg {...p}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      );
    case "sliders":
      return (
        <svg {...p}>
          <line x1="4" y1="21" x2="4" y2="14" />
          <line x1="4" y1="10" x2="4" y2="3" />
          <line x1="12" y1="21" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12" y2="3" />
          <line x1="20" y1="21" x2="20" y2="16" />
          <line x1="20" y1="12" x2="20" y2="3" />
          <line x1="1" y1="14" x2="7" y2="14" />
          <line x1="9" y1="8" x2="15" y2="8" />
          <line x1="17" y1="16" x2="23" y2="16" />
        </svg>
      );
    case "alert":
      return (
        <svg {...p}>
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );
    case "clock":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
      );
    case "pdf":
      return (
        <svg {...p}>
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <path d="M8 13h8M8 17h5" />
        </svg>
      );
    case "table":
      return (
        <svg {...p}>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
        </svg>
      );
    default:
      return <svg {...p}><circle cx="12" cy="12" r="3" /></svg>;
  }
}

function App() {
  const [conversationId, setConversationId] = useState(readStoredConversationId());
  const [conversations, setConversations] = useState([]);
  const [convBusy, setConvBusy] = useState(false);
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(() =>
    typeof window !== "undefined" ? !window.matchMedia("(max-width: 768px)").matches : true
  );

  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("groq");
  const [modelsByProvider, setModelsByProvider] = useState({});
  const [model, setModel] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [mode, setMode] = useState("auto");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ingestStatus, setIngestStatus] = useState({ has_tabular: false, has_pdf: false });
  const [files, setFiles] = useState([]);
  const [activeStored, setActiveStored] = useState([]);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [previewTarget, setPreviewTarget] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState("");
  const [filesRefreshing, setFilesRefreshing] = useState(false);
  const [maxWorkspaceFiles, setMaxWorkspaceFiles] = useState(3);
  const [maxUploadMb, setMaxUploadMb] = useState(25);
  const [showOnboarding, setShowOnboarding] = useState(() =>
    typeof window !== "undefined" ? !localStorage.getItem("askcsv_onboarding_done") : false
  );
  const dismissOnboarding = () => {
    try {
      localStorage.setItem("askcsv_onboarding_done", "1");
    } catch (e) {
      /* ignore */
    }
    setShowOnboarding(false);
  };
  const fileRef = useRef(null);
  const scrollBodyRef = useRef(null);

  const activeKey = () => "workspace_active_files:" + (datasetId || "");

  const reconcileActive = (fileList, prevList) => {
    const names = fileList.map((f) => f.stored_name);
    const nameSet = new Set(names);
    if (prevList === null) return names;
    const kept = prevList.filter((n) => nameSet.has(n));
    const prevSet = new Set(prevList);
    fileList.forEach((f) => {
      if (!prevSet.has(f.stored_name)) kept.push(f.stored_name);
    });
    return kept;
  };

  const refreshConversations = async () => {
    try {
      const list = await api.getConversations();
      setConversations(Array.isArray(list) ? list : []);
    } catch (e) {
      /* ignore */
    }
  };

  const loadConversationMessages = async (id) => {
    if (!id) return;
    setConvBusy(true);
    setError("");
    try {
      const d = await api.getConversationMessages(id);
      var arr = d && d.messages ? d.messages : [];
      setMessages(
        arr.map(function (m) {
          return { role: m.role, content: m.content, at: m.created_at || null };
        })
      );
    } catch (e) {
      setMessages([]);
    } finally {
      setConvBusy(false);
    }
  };

  const hasData = ingestStatus.has_tabular || ingestStatus.has_pdf;
  const modelOptions = useMemo(() => modelsByProvider[provider] || [], [modelsByProvider, provider]);
  const canAddMoreFiles = files.length < maxWorkspaceFiles;
  const currentTitle = useMemo(() => {
    var c = conversations.find(function (x) {
      return x.id === conversationId;
    });
    if (c && c.title) return c.title;
    return "Nouvelle discussion";
  }, [conversations, conversationId]);

  const ensureWorkspace = async () => {
    const list = await api.getDatasets();
    if (list.length) {
      const sorted = [...list].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setDatasetId(sorted[0].id);
      return sorted[0].id;
    }
    const d = await api.createDataset("Espace de travail");
    setDatasetId(d.id);
    return d.id;
  };

  const refreshDatasetMeta = async (id) => {
    if (!id) {
      setIngestStatus({ has_tabular: false, has_pdf: false });
      setFiles([]);
      return;
    }
    const [st, fl] = await Promise.all([
      api.getDatasetIngestStatus(id),
      api.getDatasetFiles(id),
    ]);
    setIngestStatus({ has_tabular: st.has_tabular, has_pdf: st.has_pdf });
    setFiles(fl.files || []);
  };

  const onRefreshFiles = async () => {
    if (!datasetId || filesRefreshing) return;
    setFilesRefreshing(true);
    try {
      await refreshDatasetMeta(datasetId);
    } catch (e) {
      /* silencieux : erreurs réseau gérées ailleurs si besoin */
    } finally {
      setFilesRefreshing(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const opts = await api.getLlmOptions();
        if (opts.options_error) setError(String(opts.options_error));
        const ps = opts.providers || [];
        setProviders(ps);
        const m = {};
        ps.forEach((p) => {
          m[p.id] = p.models || [];
        });
        setModelsByProvider(m);
        const def = opts.default_provider || (ps[0] && ps[0].id) || "groq";
        const p = ps.find((x) => x.id === def) || ps[0];
        if (p) {
          setProvider(p.id);
          const firstModel = p.models && p.models[0];
          setModel(p.default_model || firstModel || "");
        }
        await ensureWorkspace();
        try {
          const lim = await api.getLimits();
          if (lim.max_workspace_files != null) setMaxWorkspaceFiles(lim.max_workspace_files);
          if (lim.max_upload_mb != null) setMaxUploadMb(lim.max_upload_mb);
        } catch (e) {
          /* ignore */
        }
        await refreshConversations();
      } catch (e) {
        setError(String(e.message || e));
      }
    })();
  }, []);

  useEffect(() => {
    if (conversationId) localStorage.setItem("current_conversation_id", conversationId);
  }, [conversationId]);

  useEffect(() => {
    loadConversationMessages(conversationId);
  }, [conversationId]);

  useEffect(() => {
    const p = providers.find((x) => x.id === provider);
    if (!p) return;
    const choices = p.models || [];
    if (!model || (choices.length && !choices.includes(model))) {
      setModel(p.default_model || choices[0] || "");
    }
  }, [provider, providers]);

  useEffect(() => {
    refreshDatasetMeta(datasetId).catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId) return;
    if (!files.length) {
      setActiveStored([]);
      return;
    }
    let raw = localStorage.getItem(activeKey());
    let prevList = null;
    if (raw !== null) {
      try {
        prevList = JSON.parse(raw);
      } catch (e) {
        prevList = null;
      }
    }
    const next = reconcileActive(files, prevList);
    setActiveStored(next);
  }, [datasetId, files]);

  useEffect(() => {
    if (!datasetId) return;
    localStorage.setItem(activeKey(), JSON.stringify(activeStored));
  }, [datasetId, activeStored]);

  useEffect(() => {
    const run = () => {
      const el = scrollBodyRef.current;
      if (!el) return;
      el.scrollTop = el.scrollHeight;
    };
    run();
    const t1 = setTimeout(run, 0);
    const t2 = setTimeout(run, 80);
    const t3 = setTimeout(run, 250);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [messages, status, convBusy]);

  const openNewChat = () => {
    var id = newId();
    setConversationId(id);
    setMessages([]);
    setSidebarMobileOpen(false);
    refreshConversations();
  };

  const pickConversation = (id) => {
    setConversationId(id);
    setSidebarMobileOpen(false);
  };

  const deleteConversation = async (id, e) => {
    if (e) e.stopPropagation();
    if (!id) return;
    if (!window.confirm("Supprimer cette discussion et tout son contenu ?")) return;
    try {
      await api.deleteConversation(id);
    } catch (err) {
      setError(String(err.message || err));
      return;
    }
    await refreshConversations();
    if (conversationId === id) {
      try {
        var list = await api.getConversations();
        if (list && list.length) {
          setConversationId(list[0].id);
        } else {
          openNewChat();
        }
      } catch (err2) {
        openNewChat();
      }
    }
  };

  const uploadAuto = async (file) => {
    setError("");
    const useDataset = await ensureWorkspace();
    if (files.length >= maxWorkspaceFiles) {
      setError(`Limite atteinte: maximum ${maxWorkspaceFiles} fichiers.`);
      return;
    }
    setStatus("Import de " + file.name + "...");
    const out = await api.autoIngestFile(useDataset, file);
    setStatus("Fichier reconnu: " + out.kind + ". Import terminé.");
    await refreshDatasetMeta(useDataset);
  };

  const toggleFile = (storedName) => {
    setActiveStored((prev) => {
      const s = new Set(prev);
      if (s.has(storedName)) s.delete(storedName);
      else s.add(storedName);
      return Array.from(s);
    });
  };

  const selectAllFiles = () => {
    setActiveStored(files.map((f) => f.stored_name));
  };

  const selectNoFiles = () => {
    setActiveStored([]);
  };

  const confirmRemoveFile = (f) => {
    setPendingDelete(f);
  };

  const deleteFile = async () => {
    const f = pendingDelete;
    if (!f || !datasetId) {
      setPendingDelete(null);
      return;
    }
    setPendingDelete(null);
    setError("");
    try {
      await api.deleteDatasetFile(datasetId, f.stored_name);
      setActiveStored((prev) => prev.filter((x) => x !== f.stored_name));
      await refreshDatasetMeta(datasetId);
      setStatus("Fichier supprimé.");
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const openPreview = async (f) => {
    setPreviewTarget(f);
    setPreviewData(null);
    setPreviewErr("");
    setPreviewLoading(true);
    try {
      const d = await api.getFilePreview(datasetId, f.stored_name);
      setPreviewData(d);
    } catch (e) {
      setPreviewErr(String(e.message || e));
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewTarget(null);
    setPreviewData(null);
    setPreviewErr("");
    setPreviewLoading(false);
  };

  const payloadActiveFiles = () => {
    if (!files.length) return undefined;
    const allNames = files.map((f) => f.stored_name);
    const set = new Set(activeStored);
    const allOn = allNames.length && allNames.every((n) => set.has(n));
    if (allOn) return null;
    return activeStored.slice();
  };

  const send = async () => {
    const q = input.trim();
    if (!q || busy) return;
    if (hasData && files.length && activeStored.length === 0) {
      setError("Sélectionne au moins un fichier pour interroger tes données.");
      return;
    }
    setBusy(true);
    setError("");
    setInput("");
    const tUser = new Date().toISOString();
    setMessages((m) => [...m, { role: "user", content: q, at: tUser }]);
    setStatus("Réponse " + provider + "...");
    try {
      let data;
      if (datasetId && hasData) {
        const af = payloadActiveFiles();
        data = await api.askDataset(datasetId, q, mode, provider, model, conversationId, af);
      } else {
        data = await api.askFree(q, provider, model, conversationId);
      }
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.answer || "",
          at: new Date().toISOString(),
          sources: Array.isArray(data.sources) ? data.sources : [],
          tools_used: Array.isArray(data.tools_used) ? data.tools_used : [],
        },
      ]);
      setStatus("");
      refreshConversations();
    } catch (e) {
      setMessages((m) => m.slice(0, -1));
      setInput(q);
      setError(String(e.message || e));
      setStatus("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      {sidebarMobileOpen && (
        <button type="button" className="sidebar-backdrop" aria-label="Fermer le menu" onClick={() => setSidebarMobileOpen(false)} />
      )}
      <aside className={"sidebar-col" + (sidebarMobileOpen ? " mobile-open" : "")}>
        <div className="sidebar-head">
          <div className="sidebar-brand">
            <img className="brand-logo" src="/assets/asknova-logo.svg" alt="AskNova" />
            <span className="brand-name glow-text">AskNova</span>
          </div>
          <div className="rowish">
            <button type="button" className="primary" style={{ flex: 1 }} onClick={openNewChat}>
              <Icon name="plus" size={18} />
              Nouvelle discussion
            </button>
          </div>
          <div className="small">Ouvre une discussion existante ou démarre une nouvelle conversation.</div>
        </div>
        <div className="conv-list-section-label">Historique</div>
        <div className="conv-list">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={"conv-item" + (conversationId === c.id ? " active" : "")}
              onClick={() => pickConversation(c.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter") pickConversation(c.id);
              }}
            >
              <div className="conv-body">
                <div className="conv-title">{c.title}</div>
                <div className="conv-meta">
                  <Icon name="message" size={14} />
                  {c.message_count} ·{" "}
                  <Icon name="clock" size={14} />
                  {new Date(c.updated_at).toLocaleString()}
                </div>
              </div>
              <button
                type="button"
                className="conv-del"
                title="Supprimer la discussion"
                aria-label="Supprimer la discussion"
                onClick={(e) => deleteConversation(c.id, e)}
              >
                <Icon name="trash" size={18} />
              </button>
            </div>
          ))}
          {!conversations.length && (
            <div className="empty-side">
              <div className="ico-wrap">
                <Icon name="message" size={26} />
              </div>
              Aucune discussion enregistrée. Envoie un premier message pour démarrer.
            </div>
          )}
        </div>
      </aside>

      <div className="main-col">
        <div className="topbar-m">
          <button type="button" className="icon-btn" onClick={() => setSidebarMobileOpen(true)} aria-label="Ouvrir les discussions">
            <Icon name="menu" size={22} />
          </button>
          <div className="title glow-text" title={currentTitle}>
            {currentTitle}
          </div>
          <button type="button" className="icon-btn primary" onClick={openNewChat} title="Nouvelle discussion" aria-label="Nouvelle discussion">
            <Icon name="plus" size={22} />
          </button>
        </div>

        <div className="top">
          <button
            type="button"
            className="settings-toggle"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((o) => !o)}
          >
            <Icon name="sliders" size={20} />
            Réglages et fichiers
            <Icon name="chevron" size={18} className={"chev" + (settingsOpen ? " open" : "")} />
          </button>
          <div className={"top-panels" + (settingsOpen ? "" : " collapsed-mobile")}>
            <div className="top-inner-scroll">
              <div className="panel panel--compact">
                <div className="compact-grid">
                  <div className="field-group">
                    <span className="lbl">Fournisseur</span>
                    <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                      {providers.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field-group">
                    <span className="lbl">Modèle</span>
                    <select value={model} onChange={(e) => setModel(e.target.value)} disabled={!modelOptions.length}>
                      {modelOptions.length ? (
                        modelOptions.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))
                      ) : (
                        <option value={model}>{model || "modèle auto"}</option>
                      )}
                    </select>
                  </div>
                  <div className="field-group">
                    <span className="lbl">Données</span>
                    <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={!hasData}>
                      <option value="auto">Auto (agent + outils)</option>
                      <option value="agent">Agent</option>
                      <option value="tabular">Tableur</option>
                      <option value="docs">PDF</option>
                    </select>
                  </div>
                </div>
                {(() => {
                  const pr = providers.find((x) => x.id === provider);
                  return pr && pr.hint ? (
                    <div className="small" style={{ marginTop: 6, color: "var(--warn)" }}>
                      {pr.hint}
                    </div>
                  ) : null;
                })()}
                <div className="ingest-pills" aria-label="État des imports">
                  <span className={"ingest-pill" + (ingestStatus.has_tabular ? " ok" : "")}>
                    Tableur (CSV/Excel) : {ingestStatus.has_tabular ? "prêt" : "non importé"}
                  </span>
                  <span className={"ingest-pill" + (ingestStatus.has_pdf ? " ok" : "")}>
                    PDF : {ingestStatus.has_pdf ? "prêt" : "non importé"}
                  </span>
                </div>
                <div className="compact-toolbar-files">
                  <input
                    ref={fileRef}
                    type="file"
                    className="hidden"
                    accept=".pdf,.csv,.xls,.xlsx"
                    onChange={(e) => {
                      const f = e.target.files && e.target.files[0];
                      if (f) uploadAuto(f).catch((err) => setError(String(err.message || err)));
                      e.target.value = "";
                    }}
                  />
                  <button className="primary" disabled={!canAddMoreFiles} onClick={() => fileRef.current && fileRef.current.click()}>
                    <Icon name="upload" size={16} />
                    Fichier
                  </button>
                  <button
                    type="button"
                    className={"ghost is-refresh-btn" + (filesRefreshing ? " is-refreshing" : "")}
                    onClick={onRefreshFiles}
                    disabled={!datasetId || filesRefreshing}
                    title={filesRefreshing ? "Actualisation…" : "Actualiser la liste des fichiers"}
                    aria-busy={filesRefreshing}
                  >
                    <Icon name="refresh" size={16} className={filesRefreshing ? "icon-spin" : ""} />
                  </button>
                  {files.length ? (
                    <>
                      <button type="button" className="ghost" onClick={selectAllFiles} title="Tout inclure">
                        <Icon name="check" size={16} />
                      </button>
                      <button type="button" className="ghost" onClick={selectNoFiles} title="Tout exclure">
                        <Icon name="x" size={16} />
                      </button>
                    </>
                  ) : null}
                  <span className="files-badge" title="Fichiers dans l'espace">
                    {files.length}/{maxWorkspaceFiles}
                  </span>
                  <div className="files">
                    {files.length ? (
                      files.map((f) => {
                        const on = activeStored.indexOf(f.stored_name) >= 0;
                        const ik = fileKindIcon(f.kind);
                        return (
                          <div
                            key={f.stored_name}
                            className={"file-chip " + (on ? "on" : "off")}
                            onClick={() => toggleFile(f.stored_name)}
                            title={on ? "Exclure de l'analyse" : "Inclure dans l'analyse"}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                toggleFile(f.stored_name);
                              }
                            }}
                          >
                            <Icon name={ik} size={16} />
                            <span className="fname">
                              {f.kind}: {f.original_name}
                            </span>
                            <button
                              type="button"
                              className="pv"
                              title="Aperçu du fichier"
                              aria-label="Aperçu du fichier"
                              onClick={(e) => {
                                e.stopPropagation();
                                openPreview(f);
                              }}
                            >
                              <Icon name="eye" size={14} />
                            </button>
                            <button
                              type="button"
                              className="rm"
                              title="Supprimer du workspace"
                              aria-label="Supprimer du fichier"
                              onClick={(e) => {
                                e.stopPropagation();
                                confirmRemoveFile(f);
                              }}
                            >
                              <Icon name="x" size={14} />
                            </button>
                          </div>
                        );
                      })
                    ) : (
                      <span className="small" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Icon name="file" size={14} />
                        Aucun fichier
                      </span>
                    )}
                  </div>
                </div>
                {!canAddMoreFiles && (
                  <div className="small" style={{ marginTop: 6, color: "#ffb4b8", display: "flex", alignItems: "center", gap: 6 }}>
                    <Icon name="alert" size={14} />
                    Limite fichiers atteinte.
                  </div>
                )}
                {!hasData && (
                  <div className="hint hint--inline">
                    <Icon name="sparkles" size={18} />
                    <span>
                      <strong>Chat libre</strong> — importe un CSV, Excel ou PDF pour interroger tes données.
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="scroll-body" ref={scrollBodyRef}>
          <div className="chat-wrap">
            <div className="chat">
              {convBusy && (
                <div className="load-line">
                  <Icon name="refresh" size={18} className="icon-spin" />
                  <span>Chargement de la discussion…</span>
                  <span className="skel" />
                </div>
              )}
              {!convBusy && !messages.length && (
                <div className="welcome-card">
                  <div className="w-ico">
                    <Icon name="message" size={28} />
                  </div>
                  <h2>Bienvenue</h2>
                  <p>
                    Discute librement avec le modèle, ou importe des fichiers pour analyser tableurs et documents PDF. Les réponses sur tes données affichent la
                    requête SQL ou les extraits de document pour vérifier.
                  </p>
                </div>
              )}
              {!convBusy &&
                messages.map((m, i) => (
                  <div key={i} className={"bubble " + m.role}>
                    <div className="bubble-header">
                      <div className="bubble-label">
                        {m.role === "user" ? (
                          <>
                            <Icon name="message" size={14} /> Toi
                          </>
                        ) : (
                          <>
                            <Icon name="sparkles" size={14} /> Assistant
                          </>
                        )}
                      </div>
                      {m.at ? (
                        <time className="bubble-time" dateTime={m.at}>
                          {formatMsgTime(m.at)}
                        </time>
                      ) : null}
                    </div>
                    {m.content}
                    {m.role === "assistant" && m.tools_used && m.tools_used.length ? (
                      <div className="tools-hint" title="Outils invoqués par l'agent sur ce tour">
                        Outils :{" "}
                        {m.tools_used.map((t, i) => (
                          <React.Fragment key={t + "-" + i}>
                            {i > 0 ? ", " : null}
                            <kbd>{t}</kbd>
                          </React.Fragment>
                        ))}
                      </div>
                    ) : null}
                    {m.role === "assistant" && m.sources && m.sources.length ? <SourcesList sources={m.sources} /> : null}
                  </div>
                ))}
            </div>
          </div>
        </div>

        <div className="composer">
          <div className="composer-row">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Écris ton message…"
              disabled={busy || convBusy}
              aria-label="Message"
            />
            <button
              type="button"
              className="primary send-btn"
              onClick={send}
              disabled={busy || convBusy || !input.trim()}
              title="Envoyer"
              aria-label="Envoyer le message"
            >
              {busy ? <Icon name="refresh" size={22} className="icon-spin" /> : <Icon name="send" size={22} />}
            </button>
          </div>
          <div className="composer-hint">
            <Icon name="message" size={14} />
            <span>
              <kbd>Entrée</kbd> envoie · <kbd>Maj</kbd> + <kbd>Entrée</kbd> nouvelle ligne
            </span>
          </div>
          {status ? (
            <div className="status-pill">
              {busy ? <Icon name="refresh" size={16} className="icon-spin" /> : <Icon name="sparkles" size={16} />}
              {status}
            </div>
          ) : null}
          {error ? (
            <div className="err-banner" role="alert">
              <Icon name="alert" size={20} />
              <span>{error}</span>
            </div>
          ) : null}
        </div>

        <footer className="app-footer" role="contentinfo" aria-label="Pied de page">
          <div className="footer-inner">
            <div className="footer-brand">
              <div className="footer-name glow-text">RAKOTOAHIJOHN Tsioritiana Ryan</div>
              <div className="footer-sub">tsioritianaryan@gmail.com</div>
            </div>

            <div className="footer-links" aria-label="Liens de contact">
              <a className="footer-link" href="mailto:tsioritianaryan@gmail.com">tsioritianaryan@gmail.com</a>
              <a className="footer-link" href="https://github.com/RyanGitproj/" target="_blank" rel="noreferrer">
                GitHub
              </a>
            </div>

            <div className="footer-meta">
              <span>© {new Date().getFullYear()} RAKOTOAHIJOHN Tsioritiana Ryan. Tous droits réservés.</span>
            </div>
          </div>
        </footer>

        {showOnboarding && (
          <div className="modal-bg" onClick={dismissOnboarding} role="presentation">
            <div
              className="modal"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-labelledby="onb-title"
              style={{ maxWidth: 440 }}
            >
              <h3 id="onb-title">Démarrage rapide</h3>
              <p style={{ marginBottom: 12 }}>
                <strong>1.</strong> Un espace de travail est créé automatiquement pour tes fichiers.
              </p>
              <p style={{ marginBottom: 12 }}>
                <strong>2.</strong> Importe un CSV, Excel ou PDF (jusqu'à {maxWorkspaceFiles} fichiers, {maxUploadMb} Mo max chacun).
              </p>
              <p style={{ marginBottom: 0 }}>
                <strong>3.</strong> Pose une question : avec des données importées, la réponse inclut la requête SQL ou les extraits PDF pour contrôle.
              </p>
              <div className="actions">
                <button type="button" className="primary" onClick={dismissOnboarding}>
                  Compris, commencer
                </button>
              </div>
            </div>
          </div>
        )}

        {previewTarget && (
          <div className="modal-bg preview-overlay" onClick={closePreview} role="presentation">
            <div
              className="modal preview-modal"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-labelledby="pv-title"
            >
              <h3 id="pv-title">{previewTarget.original_name}</h3>
              <p className="small" style={{ marginTop: -4, marginBottom: 12 }}>
                {previewTarget.kind === "tabular" ? "Tableur" : "PDF"} · {previewTarget.stored_name}
              </p>
              {previewLoading ? (
                <div className="load-line">
                  <Icon name="refresh" size={18} className="icon-spin" />
                  <span>Chargement de l'aperçu…</span>
                </div>
              ) : null}
              {previewErr ? (
                <div className="err-banner" role="alert">
                  <Icon name="alert" size={20} />
                  <span>{previewErr}</span>
                </div>
              ) : null}
              {!previewLoading && previewData && previewData.kind === "pdf" ? (
                <div className="preview-body-scroll">
                  <div className="preview-frame">
                    <iframe
                      title={previewTarget.original_name}
                      src={api.getFileRawUrl(datasetId, previewTarget.stored_name)}
                    />
                  </div>
                  {previewData.truncated ? (
                    <p className="small" style={{ margin: "8px 0" }}>
                      Extrait texte partiel (limite configurée côté serveur).
                    </p>
                  ) : null}
                  {previewData.pages && previewData.pages.length ? (
                    <div className="preview-text-pages">
                      {previewData.pages.map((pg, idx) => (
                        <div key={idx} style={{ marginBottom: 10 }}>
                          <div className="pg-label">Page {pg.page}</div>
                          <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{pg.text || "(vide)"}</div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {!previewLoading && previewData && previewData.kind === "tabular" ? (
                <div>
                  <p className="small" style={{ marginBottom: 8 }}>
                    {previewData.total_rows_estimate != null
                      ? `Environ ${previewData.total_rows_estimate} ligne(s) dans ce fichier.`
                      : ""}{" "}
                    {previewData.truncated ? "Aperçu tronqué." : ""}
                  </p>
                  <div className="modal-table-wrap">
                    {previewData.rows && previewData.rows.length ? (
                      <table className="preview-table">
                        <thead>
                          <tr>
                            {(previewData.columns || []).map((col) => (
                              <th key={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.rows.map((row, ri) => (
                            <tr key={ri}>
                              {(previewData.columns || []).map((col) => (
                                <td key={col}>{row[col] != null ? String(row[col]) : ""}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className="small">Aucune ligne à afficher.</p>
                    )}
                  </div>
                </div>
              ) : null}
              <div className="actions">
                <button type="button" className="ghost" onClick={closePreview}>
                  Fermer
                </button>
                <a
                  className="primary"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "8px 14px",
                    textDecoration: "none",
                    borderRadius: "var(--radius-sm)",
                    fontWeight: 600,
                  }}
                  href={api.getFileRawUrl(datasetId, previewTarget.stored_name)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Ouvrir / télécharger
                </a>
              </div>
            </div>
          </div>
        )}

        {pendingDelete && (
          <div className="modal-bg" onClick={() => setPendingDelete(null)} role="presentation">
            <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="del-title">
              <h3 id="del-title">Supprimer le fichier ?</h3>
              <p>
                « <strong style={{ color: "var(--text)" }}>{pendingDelete.original_name}</strong> » sera retiré de l'espace de travail. Cette action est
                définitive.
              </p>
              <div className="actions">
                <button type="button" className="ghost" onClick={() => setPendingDelete(null)}>
                  Annuler
                </button>
                <button type="button" className="primary" onClick={deleteFile}>
                  <Icon name="trash" size={18} />
                  Supprimer
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
