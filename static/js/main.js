// Shared helpers: toasts, mobile menu, CSRF token.
const CSRF = document.body.dataset.csrf;

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = message;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.remove(), 5000);
}
document.querySelectorAll(".toast").forEach(t => setTimeout(() => t.remove(), 5000));

const menuBtn = document.getElementById("menuBtn");
if (menuBtn) menuBtn.addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
