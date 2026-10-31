/* Widget de chat Fusée — à inclure sur un site :
   <script src="https://ADRESSE-PUBLIQUE/public/chat.js" data-site="nom-du-site" data-color="#7c5cff"></script> */
(function () {
  var me = document.currentScript, base = me.src.replace(/\/public\/chat\.js.*$/, "");
  var site = me.getAttribute("data-site") || location.hostname, color = me.getAttribute("data-color") || "#7c5cff";
  var title = me.getAttribute("data-title") || "Une question ? On vous répond !";
  var KEY = "fusee_chat_" + site, st = {};
  try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
  if (!st.session) { st.session = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()); }
  st.after = st.after || 0; st.log = st.log || [];
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  save();
  var css = "#fz-btn{position:fixed;right:20px;bottom:20px;width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;" +
    "background:" + color + ";color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:2147483000}" +
    "#fz-box{position:fixed;right:20px;bottom:90px;width:340px;max-width:calc(100vw - 32px);height:460px;max-height:70vh;background:#fff;color:#111;" +
    "border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.3);display:none;text-align:left;flex-direction:column;overflow:hidden;z-index:2147483000;font:14px/1.4 system-ui,sans-serif}" +
    "#fz-box.open{display:flex}#fz-h{background:" + color + ";color:#fff;padding:12px 14px;font-weight:600}" +
    "#fz-m{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:6px;background:#f6f7fb}" +
    ".fz-b{max-width:82%;padding:8px 11px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}" +
    ".fz-in{align-self:flex-end;background:" + color + ";color:#fff}.fz-out{align-self:flex-start;background:#fff;border:1px solid #e3e5ee}" +
    "#fz-f{display:flex;border-top:1px solid #e3e5ee}#fz-t{flex:1;border:0;padding:12px;font:inherit;outline:none;resize:none}" +
    "#fz-s{border:0;background:none;color:" + color + ";font-weight:700;padding:0 14px;cursor:pointer}" +
    "#fz-e{border:0;border-top:1px solid #e3e5ee;padding:8px 12px;font:inherit;outline:none}.fz-typing{color:#888;font-size:12px}";
  var s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
  var btn = document.createElement("button"); btn.id = "fz-btn"; btn.setAttribute("aria-label", "Discuter"); btn.textContent = "💬";
  var box = document.createElement("div"); box.id = "fz-box";
  box.innerHTML = '<div id="fz-h"></div><div id="fz-m"></div><input id="fz-e" type="email" placeholder="Votre e-mail (facultatif, pour vous recontacter)">' +
    '<form id="fz-f"><textarea id="fz-t" rows="1" placeholder="Votre message…"></textarea><button id="fz-s">Envoyer</button></form>';
  document.body.appendChild(btn); document.body.appendChild(box);
  var $ = function (id) { return box.querySelector("#" + id); };
  $("fz-h").textContent = title;
  if (st.email) { $("fz-e").value = st.email; }
  function add(dir, text) {
    var d = document.createElement("div"); d.className = "fz-b " + (dir === "in" ? "fz-in" : "fz-out"); d.textContent = text;
    $("fz-m").appendChild(d); $("fz-m").scrollTop = 1e9;
  }
  if (!st.log.length) add("out", "Bonjour 👋 Comment pouvons-nous vous aider ?");
  st.log.forEach(function (m) { add(m.d, m.t); });
  var typing = null;
  function setTyping(on) {
    if (on && !typing) { typing = document.createElement("div"); typing.className = "fz-typing"; typing.textContent = "Réponse en cours…"; $("fz-m").appendChild(typing); }
    if (!on && typing) { typing.remove(); typing = null; }
    $("fz-m").scrollTop = 1e9;
  }
  var waiting = false;
  function poll() {
    fetch(base + "/public/chat/poll?session=" + encodeURIComponent(st.session) + "&after=" + st.after)
      .then(function (r) { return r.json(); }).then(function (r) {
        (r.messages || []).forEach(function (m) {
          st.after = Math.max(st.after, m.id);
          if (m.direction === "out") { setTyping(false); waiting = false; add("out", m.content); st.log.push({d: "out", t: m.content}); }
        });
        save();
      }).catch(function () {});
  }
  setInterval(function () { if (box.classList.contains("open") || waiting) poll(); }, 4000);
  btn.onclick = function () { box.classList.toggle("open"); if (box.classList.contains("open")) { poll(); $("fz-t").focus(); } };
  $("fz-t").onkeydown = function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("fz-f").requestSubmit(); } };
  $("fz-f").onsubmit = function (e) {
    e.preventDefault();
    var t = $("fz-t").value.trim(); if (!t) return;
    st.email = $("fz-e").value.trim(); $("fz-t").value = "";
    add("in", t); st.log.push({d: "in", t: t}); save();
    fetch(base + "/public/chat/send", {method: "POST", headers: {"Content-Type": "text/plain"},
      body: JSON.stringify({session: st.session, message: t, site: site, email: st.email})})
      .then(function (r) { if (r.status === 429) add("out", "Trop de messages pour le moment, réessayez un peu plus tard 🙏"); else { waiting = true; setTyping(true); } })
      .catch(function () { add("out", "Connexion impossible pour le moment, réessayez plus tard."); });
  };
})();
