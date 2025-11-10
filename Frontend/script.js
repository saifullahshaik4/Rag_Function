const API = "http://127.0.0.1:8000/api/generate";
const EXPORT_API = "http://127.0.0.1:8000/api/export/xlsx";
const out = document.getElementById("output");
const btn = document.getElementById("go");

// Store the latest stories for export
let currentStories = [];

btn.addEventListener("click", async () => {
  out.innerHTML = "";
  const f = document.getElementById("file").files[0];
  const maxStories = document.getElementById("maxStories").value || 3;
  if (!f) {
    out.innerHTML = `<p>Please choose a file.</p>`;
    return;
  }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("max_stories", maxStories);

  out.innerHTML = `<p>Processing…</p>`;
  try {
    const res = await fetch(API + `?max_stories=${maxStories}`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    render(data);
  } catch (e) {
    out.innerHTML = `<pre style="color:#b00">${e.message}</pre>`;
  }
});

function render(data) {
  const { stories = [], meta = {} } = data || {};
  
  // Store stories for export
  currentStories = stories;
  
  const parts = [];
  parts.push(
    `<div class="card"><b>Result</b><div class="muted">chunks: ${
      meta.chunks || 0
    }</div></div>`
  );
  stories.forEach((s, i) => {
    if (s.error) {
      parts.push(
        `<div class="card"><h3>${i + 1}. Error</h3><pre>${s.error}</pre></div>`
      );
      return;
    }
    const ac = (s.acceptance_criteria || [])
      .map((x) => `<div class="ac">- ${escapeHtml(x)}</div>`)
      .join("");
    const nf = (s.non_functional || []).join(", ");
    const tags = (s.tags || []).join(", ");

    parts.push(`
      <div class="card">
        <h3>${i + 1}. ${escapeHtml(s.title || "Untitled")}</h3>
        <p><b>Story</b>: ${escapeHtml(s.story || "")}</p>
        <p><b>Acceptance Criteria</b>:</p>
        ${ac}
        <p><b>Non-Functional</b>: ${escapeHtml(nf)}</p>
        <p><b>Priority</b>: ${escapeHtml(s.priority || "")}</p>
        <p><b>Tags</b>: ${escapeHtml(tags)}</p>
        <details><summary>Rationale</summary><pre>${escapeHtml(
          s.rationale || ""
        )}</pre></details>
      </div>
    `);
  });

  // XLSX download button
  if (stories.length) {
    parts.push(
      `<div class="card"><button id="downloadBtn" onclick="downloadXLSX()">Download XLSX</button></div>`
    );
  }

  out.innerHTML = parts.join("\n");
}

async function downloadXLSX() {
  const btn = document.getElementById("downloadBtn");
  if (!currentStories || currentStories.length === 0) {
    alert("No stories to export");
    return;
  }
  
  try {
    // Disable button and show loading state
    btn.disabled = true;
    btn.textContent = "Generating XLSX...";
    
    // Call backend API to generate XLSX
    const response = await fetch(EXPORT_API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(currentStories),
    });
    
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || response.statusText);
    }
    
    // Get the blob from response
    const blob = await response.blob();
    
    // Create download link
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "user_stories.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    
    // Reset button
    btn.disabled = false;
    btn.textContent = "Download XLSX";
  } catch (error) {
    alert(`Error downloading XLSX: ${error.message}`);
    // Reset button
    btn.disabled = false;
    btn.textContent = "Download XLSX";
  }
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}