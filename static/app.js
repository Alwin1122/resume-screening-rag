const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string" ? detail : res.statusText || "Request failed"
    );
  }
  return data;
}

function setStatus(id, message, isError = false) {
  const el = $(id);
  el.textContent = message || "";
  el.style.color = isError ? "var(--sienna)" : "var(--muted)";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function roleHtml(roles) {
  if (!roles?.length) return "";
  return roles
    .map((r) => `<span class="role-tag">${escapeHtml(r.title || r)}</span>`)
    .join("");
}

async function loadFiles() {
  const data = await api("/api/resumes");
  const resumes = data.resumes || [];
  const total = data.total ?? resumes.length;
  const count = $("#library-count");
  if (count) {
    count.textContent = total
      ? `${total} resume(s) stored${total > resumes.length ? ` · showing latest ${resumes.length}` : ""}`
      : "";
  }
  const list = $("#file-list");
  if (!resumes.length) {
    list.innerHTML = "";
    return;
  }
  list.innerHTML = resumes
    .map(
      (r) => `
      <li>
        ${escapeHtml(r.name || r.filename)}
        ${roleHtml(r.predicted_roles)}
        <button type="button" data-del="${r.id}" aria-label="Remove">×</button>
      </li>`
    )
    .join("");
}

function showOverlay(show) {
  $("#upload-overlay").classList.toggle("hidden", !show);
}

function renderProgress(job) {
  const total = job.total || 0;
  const done = job.done || 0;
  const pct = total ? Math.round((done / total) * 100) : 0;
  $("#bar-fill").style.width = `${pct}%`;
  $("#progress-text").textContent = total
    ? `${done} / ${total} · ${job.ok || 0} saved · ${job.failed || 0} failed`
    : job.current || "Working…";
  $("#progress-file").textContent = job.current || "";
}

let activeJobId = null;
let uploadAbort = null;

async function waitForJob(jobId) {
  activeJobId = jobId;
  showOverlay(true);
  $("#cancel-upload").disabled = false;
  for (;;) {
    const job = await api(`/api/resumes/jobs/${jobId}`);
    renderProgress(job);
    if (["done", "error", "cancelled"].includes(job.status)) {
      return job;
    }
    await new Promise((r) => setTimeout(r, 450));
  }
}

function jobStatusMessage(job) {
  const extra = (job.errors || []).join(" · ");
  if (job.status === "cancelled") {
    return `Stopped. Kept ${job.ok || 0} resume(s) already indexed.${job.failed ? " Failed: " + job.failed : ""}`;
  }
  if (job.status === "error") {
    return job.current || "Upload failed.";
  }
  return `Indexed ${job.ok} resume(s).${job.failed ? " Failed: " + job.failed : ""}${extra ? " " + extra : ""}`;
}

async function uploadFiles(files) {
  if (!files.length) return;
  showOverlay(true);
  $("#cancel-upload").disabled = false;
  renderProgress({ total: 0, done: 0, current: "Sending files…" });
  const body = new FormData();
  [...files].forEach((f) => body.append("files", f));
  uploadAbort = new AbortController();
  try {
    const started = await api("/api/resumes", {
      method: "POST",
      body,
      signal: uploadAbort.signal,
    });
    const job = await waitForJob(started.id);
    setStatus(
      "#upload-status",
      jobStatusMessage(job),
      job.status === "error" || (job.status !== "cancelled" && job.ok === 0)
    );
    await loadFiles();
  } catch (err) {
    if (err.name === "AbortError") {
      setStatus("#upload-status", "Stopped before indexing started.", true);
    } else {
      setStatus("#upload-status", err.message, true);
    }
  } finally {
    activeJobId = null;
    uploadAbort = null;
    $("#cancel-upload").disabled = false;
    showOverlay(false);
  }
}

let lastIds = [];

function renderList(payload) {
  lastIds = (payload.list || []).map((r) => r.id).filter(Boolean);
  $("#ask-summary").textContent = payload.summary || "";
  $("#download-zip").classList.toggle("hidden", !lastIds.length);
  const root = $("#ask-results");
  if (!payload.list?.length) {
    root.innerHTML = `<li class="empty">No matches. Upload resumes, then ask again.</li>`;
    return;
  }
  root.innerHTML = payload.list
    .map((r) => {
      const verdict = (r.verdict || "").toLowerCase();
      return `
      <li class="search-item">
        <div class="rank">${r.rank}</div>
        <div>
          <h3>${escapeHtml(r.name)}${
            verdict
              ? ` <span class="verdict ${escapeHtml(verdict)}">${escapeHtml(verdict)}</span>`
              : ""
          }</h3>
          <p class="meta">${escapeHtml(
            [
              ...(r.predicted_roles || []).map((x) => x.title || x),
              r.email || r.filename || "",
              ...(r.also_emails || []).filter((e) => e && e !== r.email),
              r.phone || "",
              ...(r.also_phones || []).filter((p) => p && p !== r.phone),
            ]
              .filter(Boolean)
              .join(" · ")
          )}</p>
          <p>${escapeHtml(r.why || "")}</p>
        </div>
      </li>`;
    })
    .join("");
}

$("#cancel-upload").addEventListener("click", async () => {
  $("#cancel-upload").disabled = true;
  $("#progress-file").textContent = "Stopping after the current file…";
  if (uploadAbort) {
    uploadAbort.abort();
  }
  if (!activeJobId) return;
  try {
    const job = await api(`/api/resumes/jobs/${activeJobId}/cancel`, {
      method: "POST",
    });
    renderProgress(job);
  } catch (err) {
    setStatus("#upload-status", err.message, true);
  }
});

const drop = $("#dropzone");
const input = $("#file-input");
drop.addEventListener("click", () => input.click());
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  uploadFiles(e.dataTransfer.files);
});
input.addEventListener("change", (e) => uploadFiles(e.target.files));

$("#ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const preference = new FormData(e.target).get("preference") || "";
  setStatus("#ask-status", "Building the shortlist…");
  $("#ask-summary").textContent = "";
  try {
    const result = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preference }),
    });
    setStatus(
      "#ask-status",
      result.list.length ? `${result.list.length} people` : "No one matched."
    );
    renderList(result);
  } catch (err) {
    $("#download-zip").classList.add("hidden");
    setStatus("#ask-status", err.message, true);
  }
});

$("#download-zip").addEventListener("click", async () => {
  setStatus("#ask-status", "Preparing zip…");
  try {
    const res = await fetch("/api/shortlist/zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: lastIds }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(
        typeof data.detail === "string" ? data.detail : "Could not build zip"
      );
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "shortlist-resumes.zip";
    link.click();
    URL.revokeObjectURL(url);
    setStatus("#ask-status", `Downloaded ${lastIds.length} resume(s).`);
  } catch (err) {
    setStatus("#ask-status", err.message, true);
  }
});

document.addEventListener("click", async (e) => {
  const del = e.target.closest("[data-del]");
  if (!del) return;
  try {
    await api(`/api/resumes/${del.dataset.del}`, { method: "DELETE" });
    await loadFiles();
  } catch (err) {
    setStatus("#upload-status", err.message, true);
  }
});

loadFiles().catch((err) => setStatus("#upload-status", err.message, true));
