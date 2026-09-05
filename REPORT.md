# Project Report

## Resume Screening and Job Role Prediction using Retrieval-Augmented Generation (RAG)

**Type:** Academic / technical project report  
**Application:** Local web system for resume ingest, semantic shortlisting, role labels, and zip export  
**Stack:** Python, FastAPI, ChromaDB, Groq LLM, PyMuPDF / OCR  

---

## Abstract

Hiring teams receive large volumes of resumes in PDF, Word, and zip archives. Manual screening is slow, inconsistent, and weak when candidates describe the same skills in different words. This project implements a **local RAG pipeline**: resumes are parsed (including scanned PDFs via OCR), chunked, and stored as embeddings in **ChromaDB**. A recruiter query is embedded and used to retrieve nearby chunks; results are grouped per person, **near-duplicate CVs are merged**, and **Groq** ranks a small grounded set with explanations. Each resume also receives a **heuristic job-role prediction** from titles and skills. Original files stay on disk so a shortlist can be downloaded as a zip. The system is a decision-support tool, not an automated rejector. Bulk upload runs in a **background job** with a progress overlay so large zips do not time out in a single HTTP request.

---

## 1. Introduction

### 1.1 Background

Applicant Tracking Systems (ATS) often rely on keyword filters. A candidate who writes “REST APIs in Python” may be missed by a filter that only looks for “FastAPI.” Dense **embeddings** represent meaning in vector space, so paraphrase and related skills can still match. **Retrieval-Augmented Generation (RAG)** uses those vectors to fetch only the most relevant documents, then an LLM writes a ranked shortlist **grounded** in retrieved text, which reduces hallucination of fake people or jobs.

### 1.2 Problem statement

Design and implement a system that:

1. Ingests many resumes (including zips and image PDFs).
2. Indexes them for **semantic** search.
3. Accepts a natural-language preference (including “top N”).
4. Returns **distinct people** (not the same CV twice with a different email).
5. Optionally uses **predicted job roles** when the user names a role.
6. Exports selected original files as a zip.

### 1.3 Scope

**In scope:** local web UI, parse/OCR, chunking, Chroma, Groq ranking, role heuristics, duplicate collapse, progress for bulk ingest.

**Out of scope:** cloud hosting of CVs, trained neural role classifier, full GDPR product compliance, multi-user authentication, 100k-scale production ATS.

---

## 2. Objectives

| ID | Objective |
|----|-----------|
| O1 | Parse PDF, DOCX, TXT, and zip archives into searchable text |
| O2 | Chunk and embed resumes in a persistent local vector store |
| O3 | Retrieve by semantic similarity plus skill overlap |
| O4 | Rank with an LLM using only retrieved candidates |
| O5 | Predict likely job roles from CV text and skills |
| O6 | Merge near-duplicate resumes of the same person |
| O7 | Honour “top N” in the user question |
| O8 | Support large uploads with progress, without blocking one HTTP call |
| O9 | Keep originals on disk and zip the shortlist |

---

## 3. Literature and concepts

### 3.1 RAG

RAG has two stages: **retrieve** relevant passages from a corpus; **generate** an answer using an LLM conditioned on those passages. Compared with sending an entire corpus to the model, RAG respects **token limits**, cost, and latency. Compared with fine-tuning, RAG does not require labelled training of the LLM on every new batch of CVs.

### 3.2 Embeddings and cosine space

An embedding is a dense vector. Similar sentences lie close in direction. This project uses Chroma’s default ONNX MiniLM-style embedder (local). Distance is **cosine**; similarity is treated as approximately `1 − distance`.

### 3.3 Chunking

A whole-CV vector averages skills, education, and jobs. **Section-aware** splits (Experience, Skills, …) plus **fixed windows** (~1400 characters) with **overlap** (~220) keep local meaning and avoid losing sentences at boundaries. Hits are **aggregated per `resume_id`**.

### 3.4 Approximate nearest neighbour

Chroma uses an HNSW-style index: search is sub-linear in the number of chunks, which is appropriate when many files are ingested.

### 3.5 Hybrid ranking

Dense retrieval captures paraphrase. **Skill dictionaries** and light keyword overlap capture exact tokens (e.g. tool names). The pre-LLM score blends semantic similarity, skill match, and keywords. That is a lightweight form of **hybrid search**.

---

## 4. System architecture

```text
Browser (static HTML/JS)
        |
        | HTTP
        v
FastAPI (uvicorn, port 8000)
        |
        +-- Upload job thread --> Parse/OCR --> Skills/Roles --> Chunk --> Chroma + JSON + files
        |
        +-- Ask --> Embed query --> k-NN chunks --> Group --> Dedupe --> Groq JSON --> UI
        |
        +-- Zip shortlist --> original files from disk
```

**Client:** single page — drop zone, progress overlay, question box, ranked list, download button.

**Server:** REST APIs; no separate frontend build.

**Data (gitignored):**

| Path | Role |
|------|------|
| `data/uploads/` | Original resume files |
| `data/incoming/` | Temporary zip/files during ingest |
| `data/chroma/` | Vector index |
| `data/resumes.json` | Metadata (name, email, skills, roles, preview) |
| `data/shortlist.json` | Last shortlist for zip export |

---

## 5. Methodology

### 5.1 Ingest pipeline

1. User uploads files or a zip. The API **saves** them and returns a `job_id` immediately.
2. A **background thread** walks the zip **one file at a time** (not all bytes in RAM).
3. **Parse:** PyMuPDF → pdfminer → pypdf; if text is still too short, **OCR** (page render + RapidOCR).
4. **Profile:** regex for email/phone; heuristic name from the header.
5. **Skills:** dictionary + aliases (longest match first).
6. **Roles:** ontology of titles and skill sets; top scores above a threshold.
7. **Chunk** and **embed** into collection `resumes`.
8. Persist file on disk; batch-append JSON every 20 records.
9. Client **polls** `GET /api/resumes/jobs/{id}` until `done` or `error`. Progress shows current filename and counts.

**Limits (implementation):** up to 5,000 resumes per zip, zip up to ~800 MB, 20 MB per inner file. Scanned PDFs are much slower than text PDFs.

### 5.2 Query pipeline

1. Parse **N** from language (`top 2`, `3 candidates`). Default N if unspecified.
2. If the question is only a count, use the stored library as the pool (capped).
3. Otherwise **embed the query**, retrieve up to 24 chunks, group by resume, score, **collapse duplicates**.
4. Expand pool if needed so Groq sees several **distinct** people.
5. Groq returns JSON: summary, rank, verdict, fit, why.
6. Merge LLM IDs with stored records; collapse duplicates again; **cut to N**.
7. Save shortlist; UI may zip originals.

### 5.3 Duplicate detection

Contact details are stripped. Character **shingles** and **Jaccard** overlap, plus name/phone/email rules, detect the same person with a different email or layout. One record is kept; extra emails can be attached.

### 5.4 Job role prediction

Not a trained BERT classifier. Each role has **keywords** (e.g. “frontend”) and **skills**. Score mixes title hits and skill overlap. Stored as `predicted_roles` and shown in the UI. Used in the LLM context when the user asks for a role.

---

## 6. Implementation

### 6.1 Modules

| Module | Responsibility |
|--------|----------------|
| `app/main.py` | FastAPI routes |
| `app/jobs.py` | Background ingest + progress |
| `app/parsers.py` | Zip walk, PDF/DOCX/OCR |
| `app/chunker.py` | Sections and windows |
| `app/store.py` | Files, JSON, Chroma |
| `app/matcher.py` | Vector query and hybrid score |
| `app/llm.py` | Groq ranking, top-N parse |
| `app/skills.py` | Skill lexicon |
| `app/roles.py` | Role ontology |
| `app/dedupe.py` | Same-person merge |
| `static/` | UI |

### 6.2 Main APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Web UI |
| GET | `/api/resumes` | Count + latest ~80 names |
| POST | `/api/resumes` | Start ingest job |
| GET | `/api/resumes/jobs/{id}` | Job progress |
| DELETE | `/api/resumes/{id}` | Remove file + vectors |
| POST | `/api/ask` | RAG shortlist |
| POST | `/api/shortlist/zip` | Download originals |

### 6.3 LLM

Groq chat completions, low temperature (~0.2), JSON object mode. Fallback model IDs if one is retired. System prompt: no invented people; honour N; do not invent a job title unless the user named one.

### 6.4 Security notes (project level)

- API key empty in git; local `config.py` or `GROQ_API_KEY` env.
- `.gitignore`: `data/`, `.venv/`, `.env`.
- Zip: skip `..`, `__MACOSX`, unknown extensions, oversized entries.
- Resume PII stays local; excerpts sent to Groq are a **third-party** processing trade-off.

---

## 7. User interface

1. Drop zone for files/zip; overlay with bar, `done/total`, current file.
2. Library count; chips for recent names and predicted roles.
3. Question box (e.g. `top 2 with Python`).
4. Ranked cards: name, role, email, explanation.
5. **Download shortlist zip**.

No extra “library / match / settings” tabs: one screening desk.

---

## 8. Results and usage

Typical flow: install Python packages → set Groq key locally → `start.bat` → http://127.0.0.1:8000 → upload → wait for overlay → ask → zip.

**Expected behaviour**

- “Top 2” returns two **distinct** people, not eight padded rows.
- Same CV, different email → one person.
- Role labels appear after ingest (and for older records on list load).
- Text PDFs scale to large zips better than OCR scans.

Runbook: **STEPS.md**. Oral exam: **VIVA.md**.

---

## 9. Evaluation (how the work can be judged)

There is no single accuracy number without a labelled test set. Suitable measures:

| Measure | Meaning |
|---------|---------|
| Precision@K | Of K shown people, how many are relevant |
| Recall@K | Of all relevant people, how many appear in top K |
| Duplicate F1 | Correct same-person merges vs false merges |
| Parse/OCR recall | Share of files with usable text |
| Latency | Time per text PDF vs scan; bulk job duration |
| Human agreement | Recruiter vs system shortlist |

Unit-test ideas: `parse_limit("top 2")`, Jaccard on same body different email, zip path `..` rejected, role score when title and skills match.

---

## 10. Limitations

1. Role labels are **heuristics**, not a supervised model.
2. OCR errors reduce retrieval and role quality.
3. In-memory job state is lost if the server restarts mid-upload.
4. Groq quota, deprecations, and network affect ranking.
5. Embeddings/LLMs can reflect **bias**; the tool must not auto-reject.
6. UI lists only recent names; full search still uses the index.
7. Not a production multi-tenant ATS (no auth, no audit log).

---

## 11. Future work

- Persistent job queue (Redis/SQLite) and resume-after-crash.
- Cross-encoder **reranker** after first-stage retrieval.
- Full BM25 + dense hybrid index.
- Supervised role classifier if labelled CVs exist.
- Language detection and non-English OCR.
- User accounts, audit trail, retention policy for real hiring.

---

## 12. Conclusion

The project delivers an end-to-end **RAG resume screening** system with **job-role hints**, duplicate merging, Groq-grounded ranking, bulk ingest with progress, and zip export of originals. It demonstrates embeddings, vector search, chunking, LLM grounding, and practical document engineering (PDF/OCR/zip). It is suitable as an academic prototype and as a local recruiter aid, provided humans remain in the loop.

---

## 13. References (concepts)

1. Retrieval-Augmented Generation for knowledge-intensive NLP (Lewis et al., concept of retrieve-then-generate).  
2. Sentence embeddings / MiniLM-style dual encoders for semantic similarity.  
3. HNSW approximate nearest neighbour graphs.  
4. Hybrid dense–sparse retrieval (embeddings + lexical overlap).  
5. FastAPI and persistent embedding stores (Chroma) for local RAG applications.

*(Exact paper years and venues can be filled from the course bibliography.)*

---

## Appendix A — Software list

FastAPI, Uvicorn, ChromaDB, pypdf, PyMuPDF, pdfminer.six, RapidOCR (ONNX), python-docx, Groq SDK, python-dotenv.

## Appendix B — How to run (summary)

See **STEPS.md**. Do not commit a real Groq API key. Use `cd` into the folder that contains `start.bat`.

## Appendix C — Related documents

| Document | Purpose |
|----------|---------|
| README.md | Repository overview |
| STEPS.md | Installation and daily run |
| VIVA.md | Concept viva Q&A |
| REPORT.md | This report |
