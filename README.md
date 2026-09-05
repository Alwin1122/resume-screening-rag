# Resume screening (RAG)

Local web app: upload resumes, ask who fits, get a ranked shortlist, download those files as a zip. Each CV also gets a predicted job role from titles and skills.

## Docs

| File | What it is |
|------|------------|
| [STEPS.md](STEPS.md) | How to install and run |
| [VIVA.md](VIVA.md) | Concept viva questions and answers |
| [REPORT.md](REPORT.md) | Detailed project report |
| [FAQ.md](FAQ.md) | Pointers to the files above |

## Quick start

1. `cd` into this project folder (the folder that contains `start.bat`).
2. Put your Groq key only on your machine in `app/config.py` (`GROQ_API_KEY = ""`) or in the environment. **Do not commit a real key.**
3. First time: `python -m venv .venv` then `.\.venv\Scripts\pip.exe install -r requirements.txt`
4. Double-click `start.bat` or run uvicorn on port 8000.
5. Open http://127.0.0.1:8000

## Stack

FastAPI, ChromaDB (local embeddings), Groq for ranking, PyMuPDF / OCR for PDFs.

Uploaded files stay under `data/` (gitignored).
