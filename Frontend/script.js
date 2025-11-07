const API = "http://127.0.0.1:8000/api/generate";
const out = document.getElementById("output");
const btn = document.getElementById("go");

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

  // simple CSV download built client-side
  if (stories.length) {
    const csv = toCSV(stories);
    parts.push(
      `<div class="card"><button onclick="downloadCSV(\`${csv}\`)">Download CSV</button></div>`
    );
  }

  out.innerHTML = parts.join("\n");
}

function toCSV(stories) {
  const rows = [["Summary", "Issue Type", "Description", "Priority", "Labels"]];
  for (const s of stories) {
    if (s.error) continue;
    const ac = (s.acceptance_criteria || []).map((x) => `- ${x}`).join("\n");
    const desc = `${
      s.story || ""
    }\n\nAcceptance Criteria:\n${ac}\n\nNon-Functional: ${(
      s.non_functional || []
    ).join(", ")}`;
    rows.push([
      s.title || "",
      "Story",
      desc,
      s.priority || "",
      (s.tags || []).join(","),
    ]);
  }
  // escape quotes for CSV
  return rows
    .map((r) => r.map((x) => `"${String(x).replaceAll(`"`, `""`)}"`).join(","))
    .join("\n");
}

function downloadCSV(content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "user_stories.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}