# Viva questions and answers

Concept-focused oral exam questions for this **Resume Screening and Job Role Prediction** system (RAG + Groq).

---

## 1. Project and problem

**Q. What problem does the system solve?**  
**A.** Recruiters get many resumes. Manual shortlisting is slow and inconsistent. This system stores resumes locally, retrieves the most relevant ones for a query, ranks distinct candidates with an LLM, predicts a likely job role from the CV, and exports the shortlist as a zip of original files.

**Q. Is this only keyword matching?**  
**A.** No. Keyword search fails when wording differs (e.g. “backend APIs” vs “FastAPI services”). RAG uses **embeddings** so similar *meaning* is retrieved, then an LLM explains and ranks. Skills and predicted roles add extra signals.

**Q. Screening vs job role prediction — difference?**  
**A.** **Screening** = user query → ranked people. **Role prediction** = unsupervised-style label from titles and skills on the CV (e.g. Frontend Engineer). Prediction does not replace the user’s question; it supports it when they ask for a role.

---

## 2. RAG (Retrieval-Augmented Generation)

**Q. What is RAG?**  
**A.** A pattern that **retrieves** relevant documents from a knowledge base, then **generates** an answer using an LLM **grounded** in that retrieved text. The model is not expected to invent candidates who are not in the corpus.

**Q. Why RAG instead of sending every resume to the LLM?**  
**A.** Token limits, cost, and latency. Thousands of CVs cannot fit in one prompt. Retrieval picks a small relevant subset; the LLM only ranks that subset.

**Q. What are the RAG stages in this project?**  
**A.**  
1. Parse resume → text  
2. Chunk text  
3. Embed chunks → store in Chroma  
4. Embed the user query  
5. Nearest-neighbour retrieve  
6. Deduplicate same person  
7. Groq ranks and writes “why”  
8. Optional zip of original files  

**Q. What is “grounding”?**  
**A.** The LLM may only use people and facts present in the retrieved context. That reduces hallucination of fake candidates or fake employers.

---

## 3. Embeddings and vector search

**Q. What is an embedding?**  
**A.** A dense numeric vector that represents the meaning of a piece of text. Similar sentences lie close in vector space.

**Q. Why cosine similarity (or cosine distance)?**  
**A.** It compares **direction** of vectors, not raw length, so document length is less dominant. Chroma is configured with cosine space; similarity ≈ `1 − distance`.

**Q. Why chunk resumes instead of one vector per file?**  
**A.** A long CV mixes skills, education, and jobs. One vector averages everything and can miss a relevant section. Chunks (often by section, with overlap) let retrieval hit “Experience” or “Skills” separately, then scores are **aggregated per resume**.

**Q. What model embeds the text here?**  
**A.** Chroma’s default ONNX embedding (`all-MiniLM`-style), local, no extra embedding API. Groq is used for **generation/ranking**, not for storing vectors.

---

## 4. Vector database

**Q. Why ChromaDB?**  
**A.** Persistent local vector store, simple metadata filters, no separate cloud DB. Data stays on disk under `data/chroma/`.

**Q. What is stored per chunk?**  
**A.** Chunk text, embedding, and metadata: `resume_id`, filename, name, section, chunk index. Deleting a resume deletes all chunks with that `resume_id`.

**Q. How does a query work?**  
**A.** Query text → embedding → k nearest chunks → group by `resume_id` → combine semantic score with skill overlap → unique people → LLM.

---

## 5. LLM (Groq)

**Q. What is Groq’s role?**  
**A.** Chat completion: given preference + retrieved resume excerpts, return a JSON ranked list (rank, verdict, fit, why). It does not replace retrieval.

**Q. Why structured JSON output?**  
**A.** The UI needs stable fields. `response_format: json_object` plus a schema in the system prompt. Invalid JSON is parsed from fences if needed.

**Q. How is “top 2” implemented?**  
**A.** Regex/NLP-style parse of the question (`top N`, `N candidates`). Retrieval uses a **larger pool** than N; the final list is **cut to N**. The UI must not hardcode `top_k = 8`.

**Q. Why can the LLM not invent a job role?**  
**A.** Users may only say “top 2 candidates.” Inventing “Senior Backend Engineer” changes the task. The prompt says: follow the question; use predicted roles only if the user named a role.

---

## 6. Document processing

**Q. How are PDFs read?**  
**A.** Pipeline: PyMuPDF (layout-aware text) → pdfminer → pypdf → **OCR** (render page + RapidOCR) if almost no text. Scans have no text layer; OCR is required.

**Q. Zip upload?**  
**A.** Zip is walked on disk (not all files loaded into RAM). Each PDF/DOCX/TXT is ingested one by one. RAR/7z are unsupported.

**Q. Why a background job and progress UI for large zips?**  
**A.** One HTTP request cannot OCR thousands of files before timeout. The zip is saved, a worker thread indexes files, the client **polls** job status (`done/total`, current filename).

**Q. Limits you should mention in viva?**  
**A.** About 5,000 files per zip, ~800 MB zip, text CVs scale better than scans. UI shows latest ~80 names; the full index is still used for search.

---

## 7. Duplicate detection

**Q. Why do two files look like two people?**  
**A.** Same CV, different email or template. Retrieval and the LLM treat them as two IDs.

**Q. How do you detect the same person?**  
**A.** Normalize text (strip emails/phones/URLs), compare **shingle Jaccard** overlap, plus same normalized name / phone / real email. High text overlap ⇒ same person even if email differs. Keep the better record; attach `also_emails`.

---

## 8. Job role prediction

**Q. How is a role predicted without a trained classifier?**  
**A.** A small **role ontology**: each role has title keywords and skill sets. Score = title mention in text + fraction of matching extracted skills. Top 1–2 roles above a threshold are stored.

**Q. Limitations?**  
**A.** Not a neural classifier; rare roles may be missed; OCR noise hurts keywords. It is a heuristic, not ground truth.

---

## 9. Architecture and APIs

**Q. Overall architecture?**  
**A.** FastAPI backend + static HTML/JS. Upload → parse → Chroma. Ask → retrieve → Groq. Zip endpoint streams original files for shortlist IDs.

**Q. Important endpoints?**  
**A.** `POST /api/resumes` (start ingest job), `GET /api/resumes/jobs/{id}`, `GET /api/resumes`, `POST /api/ask`, `POST /api/shortlist/zip`, `DELETE /api/resumes/{id}`.

**Q. Where should secrets live?**  
**A.** API keys in environment or local `config.py` **never committed**. `.gitignore` excludes `data/`, `.venv/`, `.env`.

---

## 10. Scoring, ranking, evaluation

**Q. How is a resume scored before the LLM?**  
**A.** Blend of: best-chunk semantic similarity, skill overlap with the query, light keyword overlap. Then unique-person collapse, then LLM reorder/explain.

**Q. How would you evaluate the system?**  
**A.** Precision@K on labelled queries, human agreement on shortlists, duplicate-merge accuracy, parse/OCR recall, latency for bulk upload. No single “accuracy %” without a labelled test set.

**Q. Failure cases?**  
**A.** Locked PDFs, bad OCR, very similar different people (false merge), query too vague, Groq key/quota errors, port already in use.

---

## 11. Short comparison questions

**Q. Fine-tuning vs RAG?**  
**A.** Fine-tuning changes model weights and needs labelled data; it still may not know *this* corpus. RAG plugs in current resumes without retraining.

**Q. TF-IDF vs embeddings?**  
**A.** TF-IDF is sparse and lexical. Embeddings capture paraphrase and related skills. This project uses embeddings for retrieval.

---

## 12. One-minute summary (if asked to conclude)

Parse and chunk resumes, embed into Chroma, retrieve by meaning, merge duplicate people, predict a likely role from skills/titles, ask Groq to rank only retrieved people, export originals as zip. That is **RAG-based resume screening** with light **role prediction**.
