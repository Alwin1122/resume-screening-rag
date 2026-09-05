# How to run

Resume shortlist is a local web app. Upload CVs, ask who fits, download that shortlist as a zip.

---

## What you need

- Windows
- Python 3.12 (or close)
- A Groq API key from [https://console.groq.com](https://console.groq.com)

---

## 1. Open the project folder

In File Explorer, go to the folder that contains `start.bat`, `app`, and `requirements.txt`.

In PowerShell:

```powershell
cd path\to\this\project
```

Example: if the project sits in your Downloads folder, that path is whatever you named it — not a fixed machine path.

---

## 2. Add the Groq key

1. Open `app/config.py`
2. Set:

```python
GROQ_API_KEY = ""
```

3. Paste your Groq key between the quotes (local machine only)
4. Save (**Ctrl+S**). Do not commit this file after adding a real key.

If you type the key but do not save, the app will not see it.

---

## 3. First-time install

From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Wait until it finishes. This can take several minutes.

---

## 4. Start the server

**Easiest:** double-click `start.bat`

**Or PowerShell** (still inside the project folder):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave that window open. You should see:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

## 5. Open the app

In a browser:

**http://127.0.0.1:8000**

---

## 6. Use it

1. Drop resumes (PDF, DOCX, TXT) or a **zip** of those files
2. Wait for the **progress screen** (file name and done / total)
3. Type a question, for example `top 2 with Python`
4. Click **Get shortlist**
5. Click **Download shortlist zip** if you want the original files

Keep the server window open until upload finishes.

---

## 7. Next time

1. Confirm the key is still in `app/config.py` and saved
2. Double-click `start.bat`
3. Open http://127.0.0.1:8000

---

## 8. Stop

In the server window, press **Ctrl+C**.

---

How to run: this file.  
Viva (concept Q&A): **VIVA.md**.  
Detailed project report: **REPORT.md**.
