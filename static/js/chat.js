// AI chat page: sends messages to /api/chat and renders replies.
const box = document.getElementById("messages");
const form = document.getElementById("chatForm");
const input = document.getElementById("chatText");
const sendBtn = document.getElementById("sendBtn");
let conversationId = box.dataset.cid ? Number(box.dataset.cid) : null;

// Escape HTML first, then apply a tiny safe markdown subset.
function format(text) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = esc.split("\n"), out = [];
  let list = null;
  const close = () => { if (list) { out.push("</" + list + ">"); list = null; } };
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    let m;
    if ((m = line.match(/^\s*(\d+)[.)]\s+(.*)/))) { if (list !== "ol") { close(); out.push("<ol>"); list = "ol"; } out.push("<li>" + m[2] + "</li>"); }
    else if ((m = line.match(/^\s*[*-]\s+(.*)/))) { if (list !== "ul") { close(); out.push("<ul>"); list = "ul"; } out.push("<li>" + m[1] + "</li>"); }
    else { close(); out.push(line.trim() ? "<p style='margin:.3rem 0'>" + line + "</p>" : ""); }
  }
  close();
  return out.join("");
}

function addMessage(role, text, extraClass = "") {
  const welcome = document.getElementById("welcome");
  if (welcome) welcome.remove();
  const wrap = document.createElement("div");
  wrap.className = "msg " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble " + extraClass;
  bubble.innerHTML = role === "assistant" ? format(text) : "";
  if (role === "user") bubble.textContent = text;
  wrap.appendChild(bubble);
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
  return bubble;
}

// Format messages already rendered by the server (saved history).
document.querySelectorAll(".msg.assistant .bubble.md").forEach(b => { b.innerHTML = format(b.textContent); });
box.scrollTop = box.scrollHeight;

async function send(text) {
  addMessage("user", text);
  const typing = addMessage("assistant", "");
  typing.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  sendBtn.disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
      body: JSON.stringify({ message: text, conversation_id: conversationId })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    typing.innerHTML = format(data.reply);
    if (data.related && data.related.length) {
      const rel = document.createElement("div");
      rel.className = "related";
      rel.innerHTML = "Related guides: " + data.related.map(a => `<a href="/kb?q=${encodeURIComponent(a.title)}">${a.title.replace(/</g, "&lt;")}</a>`).join("");
      typing.appendChild(rel);
    }
    if (!conversationId) {
      conversationId = data.conversation_id;
      history.replaceState(null, "", "/chat?c=" + conversationId);
      document.getElementById("ticketLink").href = "/tickets/new?conversation_id=" + conversationId;
      const list = document.getElementById("convoList");
      const empty = list.querySelector("p");
      if (empty) empty.remove();
      const row = document.createElement("div");
      row.className = "convo active";
      row.innerHTML = `<a href="/chat?c=${conversationId}"></a><button class="link-btn del" data-id="${conversationId}" title="Delete conversation">&times;</button>`;
      row.querySelector("a").textContent = data.title;
      list.prepend(row);
    }
  } catch (err) {
    typing.className = "bubble err";
    typing.textContent = err.message;
    toast(err.message, "error");
  } finally {
    sendBtn.disabled = false;
    input.focus();
    box.scrollTop = box.scrollHeight;
  }
}

form.addEventListener("submit", e => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || sendBtn.disabled) return;
  input.value = "";
  input.style.height = "auto";
  send(text);
});
input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});
input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; });
document.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => { input.value = c.textContent; form.requestSubmit(); }));

// Delete conversation (event delegation so new rows work too)
document.getElementById("convoList").addEventListener("click", async e => {
  const btn = e.target.closest(".del");
  if (!btn || !confirm("Delete this conversation?")) return;
  const res = await fetch(`/api/conversations/${btn.dataset.id}/delete`, { method: "POST", headers: { "X-CSRF-Token": CSRF } });
  if (!res.ok) return toast("Could not delete the conversation.", "error");
  if (Number(btn.dataset.id) === conversationId) location.href = "/chat";
  else btn.closest(".convo").remove();
});
