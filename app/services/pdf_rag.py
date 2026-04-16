from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import unicodedata
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.embeddings import get_embeddings
from app.llm import LLMError, coerce_to_llm_error, get_chat_llm
from app.services.datasets import dataset_dir, docs_dir, pdf_index_dir


_RE_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
_RE_WS = re.compile(r"[ \t\f\v]+")
_RE_MANY_NL = re.compile(r"\n{3,}")
_RE_MANY_PUNCT = re.compile(r"^[\W_]+$", re.UNICODE)
_RE_PAGE_NUM = re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*/\s*\d{1,4})?$", re.IGNORECASE)
_RE_TOKEN = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", re.UNICODE)


def normalize_text_for_indexing(text: str) -> str:
    """
    Nettoyage "safe" avant embeddings (RAG):
    - normalisation Unicode (NFKC)
    - suppression caractères de contrôle (hors \\n/\\t)
    - correction césures "mot-\\nmot"
    - réduction whitespace
    Objectif: améliorer la recherche vectorielle sans dénaturer la sémantique (pas de stop-words).
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("\u00a0", " ")  # NBSP -> space

    # Retire contrôles invisibles (garde newline/tab).
    t = "".join(ch for ch in t if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C")

    # Césures de fin de ligne: "infor-\nmation" -> "information"
    t = _RE_HYPHEN_LINEBREAK.sub(r"\1\2", t)

    # Normalise whitespace sans tout aplatir: limite les suites de lignes vides.
    t = _RE_WS.sub(" ", t)
    t = _RE_MANY_NL.sub("\n\n", t)
    return t.strip()


def _normalize_boilerplate_line(line: str) -> str:
    t = (line or "").strip()
    if not t:
        return ""
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("\u00a0", " ")
    t = _RE_WS.sub(" ", t).strip()
    return t


def _is_candidate_boilerplate(line: str) -> bool:
    """
    Heuristique conservative: on ne retire que des lignes "courtes" et très répétées
    trouvées en haut/bas des pages.
    """
    t = _normalize_boilerplate_line(line)
    if not t:
        return False
    if len(t) < 3 or len(t) > 120:
        return False
    if _RE_MANY_PUNCT.match(t):
        return False
    # Page number patterns are common boilerplate.
    if _RE_PAGE_NUM.match(t):
        return True
    # Must contain at least a few alphanumerics (avoid stripping decorative lines).
    alnum = sum(ch.isalnum() for ch in t)
    return alnum >= 3


def _detect_repeated_boilerplate(
    pages: list[tuple[int, str]],
    *,
    head_lines: int = 3,
    foot_lines: int = 3,
    min_ratio: float = 0.6,
) -> tuple[set[str], set[str]]:
    """
    Détecte des lignes répétées en en-tête/pied sur plusieurs pages.
    Retourne (header_set, footer_set) en texte normalisé.
    """
    if len(pages) < 3:
        return set(), set()
    head_counts: Counter[str] = Counter()
    foot_counts: Counter[str] = Counter()
    total_pages = 0

    for _page_no, text in pages:
        raw = (text or "").strip()
        if not raw:
            continue
        total_pages += 1
        lines = [ln for ln in raw.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        head = lines[:head_lines]
        foot = lines[-foot_lines:] if len(lines) >= foot_lines else lines

        for ln in head:
            if _is_candidate_boilerplate(ln):
                head_counts[_normalize_boilerplate_line(ln)] += 1
        for ln in foot:
            if _is_candidate_boilerplate(ln):
                foot_counts[_normalize_boilerplate_line(ln)] += 1

    if total_pages < 3:
        return set(), set()

    threshold = max(2, int(total_pages * min_ratio))
    header_set = {k for k, v in head_counts.items() if v >= threshold}
    footer_set = {k for k, v in foot_counts.items() if v >= threshold}
    return header_set, footer_set


def _strip_detected_boilerplate(text: str, header_set: set[str], footer_set: set[str], *, scan: int = 6) -> str:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines_all = raw.splitlines()
    if not lines_all:
        return raw.strip()

    # Work on a view with original lines preserved.
    keep = [True] * len(lines_all)

    # Mark header candidates
    for i in range(min(scan, len(lines_all))):
        t = _normalize_boilerplate_line(lines_all[i])
        if t and t in header_set:
            keep[i] = False

    # Mark footer candidates
    for j in range(max(0, len(lines_all) - scan), len(lines_all)):
        t = _normalize_boilerplate_line(lines_all[j])
        if t and t in footer_set:
            keep[j] = False

    stripped = "\n".join(ln for ln, k in zip(lines_all, keep, strict=False) if k).strip()
    return stripped


def _content_sig(text: str, *, max_chars: int = 900) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = _RE_WS.sub(" ", t)
    t = t[:max_chars]
    return hashlib.sha1(t.encode("utf-8", errors="replace")).hexdigest()


def _dedupe_documents(docs: list[Document], *, min_len: int = 80) -> list[Document]:
    """
    Déduplication conservative des chunks : évite d'indexer des passages identiques
    (headers/pieds, annexes répétées, PDF mal généré, etc.).
    """
    seen: set[str] = set()
    out: list[Document] = []
    for d in docs:
        txt = (d.page_content or "").strip()
        if len(txt) < min_len:
            out.append(d)
            continue
        sig = _content_sig(txt)
        if not sig or sig in seen:
            continue
        seen.add(sig)
        out.append(d)
    return out


def _diversify_hits(hits: list[Document], *, need: int) -> list[Document]:
    """
    Diversification simple:
    - évite trop d'extraits provenant de la même page
    - évite les duplicats de contenu
    """
    if not hits:
        return []
    out: list[Document] = []
    seen_pages: set[tuple[str, int | None]] = set()
    seen_sigs: set[str] = set()
    for d in hits:
        path = str(d.metadata.get("path") or "")
        pg = d.metadata.get("page")
        try:
            pg_i = int(pg) if pg is not None else None
        except (TypeError, ValueError):
            pg_i = None
        page_key = (path, pg_i)
        sig = _content_sig(_doc_raw_text(d) or d.page_content)
        if sig and sig in seen_sigs:
            continue
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        if sig:
            seen_sigs.add(sig)
        out.append(d)
        if len(out) >= need:
            return out
    # Fallback: si pas assez divers, complète par duplicats de pages mais uniques en contenu.
    for d in hits:
        sig = _content_sig(_doc_raw_text(d) or d.page_content)
        if sig and sig in seen_sigs:
            continue
        if sig:
            seen_sigs.add(sig)
        out.append(d)
        if len(out) >= need:
            break
    return out[:need]


def _tokenize_for_bm25(text: str) -> list[str]:
    # Tokenizer simple et robuste (FR/EN), garde chiffres & lettres accentuées.
    t = (text or "").lower()
    return _RE_TOKEN.findall(t)


def _hybrid_rerank_rrf(query: str, candidates: list[Document], *, rrf_k: int = 60) -> list[Document]:
    """
    Rerank hybride sans dépendre des scores FAISS:
    - rang vectoriel = ordre initial de `candidates`
    - rang lexical = BM25 sur le texte affichable (boilerplate retiré)
    Combine via Reciprocal Rank Fusion (RRF) pour être stable.
    """
    if not candidates:
        return []
    # Vector rank: current order.
    vec_rank: dict[int, int] = {id(d): i for i, d in enumerate(candidates)}

    corpus_tokens = [_tokenize_for_bm25(_doc_raw_text(d)) for d in candidates]
    q_tokens = _tokenize_for_bm25(query)
    if not q_tokens:
        return candidates
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(q_tokens)
    bm_order = sorted(range(len(candidates)), key=lambda i: float(scores[i]), reverse=True)
    bm_rank: dict[int, int] = {id(candidates[i]): r for r, i in enumerate(bm_order)}

    def rrf_score(doc: Document) -> float:
        vr = vec_rank.get(id(doc), 10_000)
        br = bm_rank.get(id(doc), 10_000)
        return 1.0 / (rrf_k + vr + 1) + 1.0 / (rrf_k + br + 1)

    return sorted(candidates, key=rrf_score, reverse=True)


def _doc_raw_text(d: Document) -> str:
    # Prefer a display-friendly raw text (boilerplate stripped) if present.
    disp = d.metadata.get("raw_text_display")
    if disp is not None:
        return str(disp)
    raw = d.metadata.get("raw_text")
    if raw is not None:
        return str(raw)
    return d.page_content


def _ensure_pdf_dirs(dataset_id: str) -> None:
    d = dataset_dir(dataset_id)
    d.mkdir(parents=True, exist_ok=True)
    docs_dir(dataset_id).mkdir(parents=True, exist_ok=True)
    pdf_index_dir(dataset_id).mkdir(parents=True, exist_ok=True)


def _manifest_path(dataset_id: str) -> Path:
    return docs_dir(dataset_id) / "manifest.json"


def _append_manifest(dataset_id: str, *, original_name: str, stored_name: str) -> None:
    path = _manifest_path(dataset_id)
    rows: list[dict] = []
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
    rows.append(
        {
            "kind": "pdf",
            "original_name": original_name,
            "stored_name": stored_name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_pdf_pages(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    out: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            out.append((i, text))
    if not out:
        s = get_settings()
        if s.pdf_ocr_enabled:
            from app.services.pdf_ocr import extract_pdf_pages_ocr

            out = extract_pdf_pages_ocr(path, max_pages=s.pdf_ocr_max_pages)
    return out


_RETRIEVAL_LOCK = threading.Lock()
_RETRIEVAL_CACHE: dict[str, tuple[float, tuple[str, list[dict]]]] = {}
_RETRIEVAL_CACHE_MAX = 900


def clear_pdf_retrieval_cache(dataset_id: str | None = None) -> None:
    """Invalide le cache des extraits (après ingest / rebuild). ``dataset_id`` None = tout vider."""
    with _RETRIEVAL_LOCK:
        if dataset_id is None:
            _RETRIEVAL_CACHE.clear()
            return
        prefix = f"{dataset_id}:"
        for k in list(_RETRIEVAL_CACHE.keys()):
            if k.startswith(prefix):
                del _RETRIEVAL_CACHE[k]


def _retrieval_cache_key(
    dataset_id: str,
    question: str,
    active_pdf_files: list[str] | None,
) -> str:
    allowed = ",".join(sorted(active_pdf_files)) if active_pdf_files is not None else "*"
    raw = f"{dataset_id}\x00{allowed}\x00{(question or '')[:4000]}"
    h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:40]
    return f"{dataset_id}:{h}"


_PDF_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer from the text excerpts below. They come from user-uploaded files. Infer nothing beyond what the excerpts and the user actually say.\n"
            "If the human message includes a context block (header « Fil récent » or similar) before « Question actuelle : », that line is the main instruction; use the block for pronouns, short follow-ups, and coherence with prior turns.\n"
            "Default rule: keep factual claims grounded in the excerpts.\n"
            "If the excerpts do not contain what is needed (or context is empty), do TWO things:\n"
            "1) Briefly tell the user that this is not found in the provided files (e.g. « Ce n'est pas dans le document fourni »).\n"
            "2) Then answer the user's question with a best-effort general answer, clearly labeled as « hors du document » (not verified by the uploaded text).\n"
            "Never pretend a claim comes from the excerpts if it is not supported by them.\n"
            "If the question is ambiguous, ask ONE short clarifying question instead of guessing.\n"
            "Stay faithful to the excerpts for factual claims; do not invent unsupported details.\n"
            "If the user’s message is mainly conversational (acknowledgement, thanks, brief continuation), respond naturally using the thread in their message; use excerpts only when needed to confirm a fact.\n"
            "Reply in the same language as the user's current question (the « Question actuelle » line).\n"
            "If the excerpts do not contain what is needed, do not ask the user to restart the conversation; just provide the « hors du document » best-effort answer, optionally suggesting how to rephrase for a document-backed answer.\n"
            "Be concise. Do not cite page numbers in the answer unless the user asks for references.\n\n"
            "Context snippets:\n{context}\n",
        ),
        ("human", "{question}"),
    ]
)


def _documents_from_pdf_file(dataset_id: str, stored_name: str, display_name: str) -> list[Document]:
    out_path = docs_dir(dataset_id) / stored_name
    if not out_path.exists():
        return []
    pages = _read_pdf_pages(out_path)
    header_set, footer_set = _detect_repeated_boilerplate(pages)
    docs: list[Document] = []
    for page_no, text in pages:
        raw = (text or "").strip()
        raw_display = _strip_detected_boilerplate(raw, header_set, footer_set) if raw else ""
        cleaned = normalize_text_for_indexing(raw_display or raw)
        docs.append(
            Document(
                # Important: index the cleaned text, but keep raw for excerpts/citations.
                page_content=cleaned,
                metadata={
                    "source": display_name,
                    "path": str(out_path.name),
                    "page": page_no,
                    "raw_text": raw,
                    "raw_text_display": raw_display or raw,
                },
            )
        )
    return docs


def rebuild_pdf_index_from_manifest(dataset_id: str) -> None:
    s = get_settings()
    path = _manifest_path(dataset_id)
    if not path.exists():
        idx = pdf_index_dir(dataset_id)
        if idx.exists():
            shutil.rmtree(idx)
        return
    rows = json.loads(path.read_text(encoding="utf-8"))
    pdf_rows = [r for r in rows if str(r.get("kind", "")) == "pdf"]
    if not pdf_rows:
        idx = pdf_index_dir(dataset_id)
        if idx.exists():
            shutil.rmtree(idx)
        return
    all_docs: list[Document] = []
    for r in pdf_rows:
        stored = str(r.get("stored_name", ""))
        original = str(r.get("original_name", "document.pdf"))
        all_docs.extend(_documents_from_pdf_file(dataset_id, stored, original))
    if not all_docs:
        idx = pdf_index_dir(dataset_id)
        if idx.exists():
            shutil.rmtree(idx)
        return
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
    chunks = splitter.split_documents(all_docs)
    chunks = _dedupe_documents(chunks)
    emb = get_embeddings(s)
    db = FAISS.from_documents(chunks, emb)
    idx_dir = pdf_index_dir(dataset_id)
    idx_dir.mkdir(parents=True, exist_ok=True)
    db.save_local(str(idx_dir))
    clear_pdf_retrieval_cache(dataset_id)


def _similarity_hits_filtered(
    db: FAISS,
    question: str,
    allowed_paths: set[str] | None,
    need: int = 4,
    max_k: int = 64,
) -> list[Document]:
    if allowed_paths is not None and len(allowed_paths) == 0:
        raise HTTPException(status_code=400, detail="Aucun fichier PDF sélectionné pour la requête.")
    if allowed_paths is None:
        batch = db.similarity_search(question, k=min(max(need * 8, need), max_k))
        batch = _hybrid_rerank_rrf(question, batch)
        return _diversify_hits(batch, need=need)
    k = 8
    while k <= max_k:
        batch = db.similarity_search(question, k=k)
        filtered = [d for d in batch if str(d.metadata.get("path") or "") in allowed_paths]
        if len(filtered) >= need or k >= max_k:
            filtered = _hybrid_rerank_rrf(question, filtered)
            return _diversify_hits(filtered, need=need)
        k *= 2
    return []


class PdfRagService:
    async def ingest(self, dataset_id: str, file: UploadFile) -> dict:
        s = get_settings()
        _ensure_pdf_dirs(dataset_id)

        filename = file.filename or "document.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptés.")

        content = await file.read()
        if len(content) > (s.max_upload_mb * 1024 * 1024):
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {s.max_upload_mb} Mo). Réduis la taille ou augmente MAX_UPLOAD_MB.",
            )

        file_id = str(uuid.uuid4())
        out_path = docs_dir(dataset_id) / f"{file_id}.pdf"
        out_path.write_bytes(content)
        _append_manifest(dataset_id, original_name=filename, stored_name=out_path.name)

        pages = _read_pdf_pages(out_path)
        if not pages:
            s2 = get_settings()
            ocr_hint = (
                " Tu peux activer PDF_OCR_ENABLED=true et installer l’extra « ocr » (Tesseract + Poppler) pour les scans."
                if not s2.pdf_ocr_enabled
                else " OCR activé mais aucun texte lu : vérifie Tesseract / Poppler."
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Aucun texte extractible dans ce PDF (souvent un scan ou une image). "
                    "Utilise un PDF avec du texte sélectionnable ou un pipeline OCR."
                    + ocr_hint
                ),
            )

        # Utilise le même pipeline (nettoyage + boilerplate stripping) que le rebuild.
        docs = _documents_from_pdf_file(dataset_id, out_path.name, filename)

        splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)
        chunks = splitter.split_documents(docs)
        chunks = _dedupe_documents(chunks)

        emb = get_embeddings(s)
        idx_dir = pdf_index_dir(dataset_id)
        if idx_dir.exists() and any(idx_dir.iterdir()):
            db = FAISS.load_local(str(idx_dir), emb, allow_dangerous_deserialization=True)
            db.add_documents(chunks)
        else:
            db = FAISS.from_documents(chunks, emb)
        db.save_local(str(idx_dir))
        clear_pdf_retrieval_cache(dataset_id)

        return {"dataset_id": dataset_id, "files": [filename], "chunks": len(chunks)}

    def answer(
        self,
        dataset_id: str,
        question: str,
        provider: str | None = None,
        model: str | None = None,
        active_pdf_files: list[str] | None = None,
        *,
        llm_question: str | None = None,
    ) -> tuple[str, list[dict]]:
        """`question` sert à la recherche vectorielle ; `llm_question` (si fourni) au prompt final."""
        s = get_settings()
        idx_dir = pdf_index_dir(dataset_id)
        if not idx_dir.exists():
            raise HTTPException(status_code=404, detail="No PDF index found. Ingest PDF first.")

        emb = get_embeddings(s)
        db = FAISS.load_local(str(idx_dir), emb, allow_dangerous_deserialization=True)

        allowed: set[str] | None = None
        if active_pdf_files is not None:
            allowed = set(active_pdf_files)
        q_search = (question or "").strip()
        hits = _similarity_hits_filtered(db, q_search, allowed, need=6, max_k=64)
        if hits:
            context = "\n\n".join(
                f"[{d.metadata.get('source')} p.{d.metadata.get('page')}]\n{_doc_raw_text(d)[:900]}"
                for d in hits
            )
        else:
            # Important: do not block the conversation when retrieval yields no hits.
            # The prompt will explain that the answer is « hors du document » and provide a best-effort response.
            context = ""

        q_llm = (llm_question or question or "").strip()
        try:
            llm = get_chat_llm(s, provider_override=provider, model_override=model)
            chain = _PDF_PROMPT | llm | StrOutputParser()
            answer = chain.invoke({"question": q_llm, "context": context}).strip()
        except LLMError:
            raise
        except Exception as exc:
            raise coerce_to_llm_error(exc) from exc

        sources = []
        for d in hits:
            raw = _doc_raw_text(d)
            sources.append(
                {
                    "kind": "doc",
                    "source": str(d.metadata.get("source") or "document"),
                    "page": int(d.metadata.get("page")) if d.metadata.get("page") is not None else None,
                    "excerpt": (raw[:300] + ("…" if len(raw) > 300 else "")),
                }
            )

        return answer, sources

    def retrieve_excerpts(
        self,
        dataset_id: str,
        question: str,
        active_pdf_files: list[str] | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Recherche vectorielle seule (pas de LLM). Pour un agent qui synthétise lui-même.
        """
        s = get_settings()
        ttl = int(s.pdf_retrieval_cache_ttl_seconds)
        cache_key = _retrieval_cache_key(dataset_id, question or "", active_pdf_files)
        if ttl > 0:
            now = time.time()
            with _RETRIEVAL_LOCK:
                hit = _RETRIEVAL_CACHE.get(cache_key)
                if hit and now - hit[0] < ttl:
                    return hit[1]

        idx_dir = pdf_index_dir(dataset_id)
        if not idx_dir.exists():
            return "(Aucun index PDF : importez un PDF d’abord.)", []

        emb = get_embeddings(s)
        db = FAISS.load_local(str(idx_dir), emb, allow_dangerous_deserialization=True)
        allowed: set[str] | None = None
        if active_pdf_files is not None:
            allowed = set(active_pdf_files)
        q_search = (question or "").strip()
        hits = _similarity_hits_filtered(db, q_search, allowed, need=6, max_k=64)
        if not hits:
            return "(Aucun passage pertinent trouvé dans les PDF indexés pour cette requête.)", []

        context = "\n\n".join(
            f"[{d.metadata.get('source')} p.{d.metadata.get('page')}]\n{_doc_raw_text(d)[:900]}"
            for d in hits
        )
        sources = []
        for d in hits:
            raw = _doc_raw_text(d)
            sources.append(
                {
                    "kind": "doc",
                    "source": str(d.metadata.get("source") or "document"),
                    "page": int(d.metadata.get("page")) if d.metadata.get("page") is not None else None,
                    "excerpt": (raw[:300] + ("…" if len(raw) > 300 else "")),
                }
            )
        result = (context, sources)
        if ttl > 0:
            with _RETRIEVAL_LOCK:
                if len(_RETRIEVAL_CACHE) > _RETRIEVAL_CACHE_MAX:
                    for k in list(_RETRIEVAL_CACHE.keys())[:250]:
                        _RETRIEVAL_CACHE.pop(k, None)
                _RETRIEVAL_CACHE[cache_key] = (time.time(), result)
        return result

