# app.py — MeetEase (FAST, single-file, NO DB)
# --------------------------------------------------------------------------------------
# - No database required (stores small JSON artifacts under ./cache).
# - OCR: PyMuPDF + Tesseract (optional).
# - Indexing: FAISS (if available) + BM25 with disk caching.
# - STT: faster-whisper (CTranslate2) with ffmpeg/pydub fallback.
# - LLM: OpenAI optional (fixed in code or via environment variable).
# --------------------------------------------------------------------------------------

from __future__ import annotations

import os, io, re, csv, json, time, math, pickle, hashlib, tempfile, warnings, gc, subprocess, shutil, sys
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from datetime import date, datetime

warnings.filterwarnings("ignore", category=FutureWarning)

# ============================== CONFIG ===============================
# You can override via environment variables if you want
OPENAI_MODEL       = os.getenv("MEETEASE_OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("MEETEASE_OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Embeddings
EMBED_MODE         = os.getenv("MEETEASE_EMBED_MODE", "minilm").lower()  # 'minilm' | 'openai'
MINILM_MODEL_NAME  = os.getenv("MEETEASE_MINILM", "sentence-transformers/all-MiniLM-L6-v2")

# Whisper / OCR / Tokenization
WHISPER_MODEL      = os.getenv("MEETEASE_WHISPER_MODEL", "base")
TEMPERATURE        = float(os.getenv("MEETEASE_TEMPERATURE", "0.2"))
MAX_INPUT_TOKENS   = int(os.getenv("MEETEASE_MAX_INPUT_TOKENS", "3000"))
TESSERACT_PATH_WIN = os.getenv("MEETEASE_TESSERACT_PATH", "")

# Caches & uploads
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
CACHE_DIR  = os.getenv("CACHE_DIR", "cache")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CACHE_DIR,  exist_ok=True)

# ============================== OPENAI API KEY (NO SIDEBAR) ===============================
# Replace "sk-your-key-here" with your real key or set via environment variable.
FIXED_OPENAI_KEY = os.getenv("OPENAI_API_KEY", "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")

if not FIXED_OPENAI_KEY or not FIXED_OPENAI_KEY.startswith("sk-"):
    import streamlit as st
    st.set_page_config(page_title="MeetEase — Missing Key", page_icon="❌")
    st.error("❌ OpenAI API key is missing or invalid. Please add it to the code or set it in Streamlit Secrets.")
    st.stop()

os.environ["OPENAI_API_KEY"] = FIXED_OPENAI_KEY

# ============================== UI ===============================
import streamlit as st
st.set_page_config(page_title="MeetEase — Meeting Management (No-DB)", page_icon="🎯", layout="wide")
st.markdown("""
<style>
.main .block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px;}
.big-title {font-size: 2rem; font-weight: 800; margin-bottom: .25rem;}
.subtle {color: #6b7280;}
.card {padding: 1rem 1.25rem; border: 1px solid #e5e7eb; border-radius: 14px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.04);} 
.card h4 {margin: 0 0 .5rem 0;}
.kv {display:flex; gap:.5rem; align-items:center;}
.kv b{min-width:150px; display:inline-block;}
.stButton>button {border-radius: 10px; padding: .5rem 1rem;}
textarea {border-radius: 10px !important;}
.streamlit-expanderHeader {font-weight: 700;}
.progress-wrap {border:1px solid #e5e7eb; border-radius: 10px; padding:.75rem; margin:.5rem 0;}
.small {font-size:.9rem; color:#6b7280}
.codebox {font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="big-title">🤖 MeetEase — Meeting Management (No-DB)</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Prepare, run, and summarize meetings with AI assistance — all cached locally.</div>', unsafe_allow_html=True)
st.write("")

# Confirm key loaded
st.success("✅ OpenAI API key loaded automatically from code or environment.")

# ============================== FILE STORAGE (NO DB) ===============================
def _slug(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", s.strip().lower()).strip("-")
    return re.sub(r"-+", "-", s) or "session"

def _session_id(title: str, mdate: date, doc_hash: str) -> str:
    base = f"{_slug(title)}-{mdate.isoformat()}-{doc_hash[:8]}"
    return base

def _sess_dir(session_id: str) -> str:
    d = os.path.join(CACHE_DIR, session_id)
    os.makedirs(d, exist_ok=True)
    return d

def _write_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")

def _read_text(path: str) -> str:
    if not os.path.isfile(path): return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _write_json(path: str, obj: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _read_json(path: str) -> Dict:
    if not os.path.isfile(path): return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ============================== OCR / FILES ===============================
from PIL import Image
import numpy as np
import pytesseract
import fitz  # PyMuPDF
import docx
import cv2

if TESSERACT_PATH_WIN:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH_WIN

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def settings_hash(d: Dict) -> str:
    s = json.dumps(d, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

# (The rest of your code remains **identical** to the version you pasted —
# including tokenizers, embeddings, FAISS, OCR, Whisper STT, RAG, tabs, and summaries.)
# I’m truncating here to save space but your full logic continues seamlessly.

# ============================== REST OF CODE (unchanged) ===============================
# Paste everything from your original file below this line,
# starting from the tokenizer section:
#     @st.cache_resource(show_spinner=False)
#     def token_encoder_cached():
#         ...
# (and continue through all tabs: Pre-Meeting, Agenda, Tracking, Summary, etc.)
