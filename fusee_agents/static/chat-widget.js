/* Widget de chat Fusée — à inclure sur un site :
   <script src="https://ADRESSE-PUBLIQUE/public/chat.js" data-site="nom-du-site" data-color="#7c5cff"></script>
   Le visiteur peut écrire ou PARLER (🎤) : la dictée et la lecture à voix haute sont faites par son navigateur,
   Fusée ne reçoit que du texte. */
(function () {
  var me = document.currentScript, base = me.src.replace(/\/public\/chat\.js.*$/, "");
  var site = me.getAttribute("data-site") || location.hostname, color = me.getAttribute("data-color") || "#7c5cff";
  var title = me.getAttribute("data-title") || "Une question ? On vous répond !";
  // statistiques : le widget de chat charge aussi le compteur de visites
  if (!window.__fuseeA) { var t = document.createElement("script"); t.src = base + "/public/a.js"; t.setAttribute("data-site", site); document.head.appendChild(t); }
  function track(ev) { if (window.fuseeTrack) window.fuseeTrack(ev); }
  var KEY = "fusee_chat_" + site, st = {};
  try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
  if (!st.session) { st.session = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()); }
  st.after = st.after || 0; st.log = st.log || [];
  if (st.speak === undefined) st.speak = true;
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  save();

  // --- voix (si le navigateur sait faire) ---
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  var lang = document.documentElement.lang || navigator.language || "fr-FR";
  if (navigator.language && navigator.language.toLowerCase().indexOf(lang.toLowerCase()) === 0) lang = navigator.language;

  var css = "#fz-btn{position:fixed;right:20px;bottom:20px;width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;" +
    "background:" + color + ";color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:2147483000}" +
    "#fz-box{position:fixed;right:20px;bottom:90px;width:340px;max-width:calc(100vw - 32px);height:460px;max-height:70vh;background:#fff;color:#111;" +
    "border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.3);display:none;text-align:left;flex-direction:column;overflow:hidden;z-index:2147483000;font:14px/1.4 system-ui,sans-serif}" +
    "#fz-box.open{display:flex}#fz-h{background:" + color + ";color:#fff;padding:10px 14px;font-weight:600;display:flex;align-items:center;gap:8px}" +
    "#fz-h span{flex:1}#fz-h small{display:block;font-weight:400;font-size:11px;opacity:.85}" +
    "#fz-x,#fz-v{background:none;border:0;color:#fff;font-size:18px;line-height:1;cursor:pointer;padding:0 4px}" +
    "#fz-m{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:6px;background:#f6f7fb}" +
    ".fz-b{max-width:82%;padding:8px 11px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word}" +
    ".fz-in{align-self:flex-end;background:" + color + ";color:#fff}.fz-out{align-self:flex-start;background:#fff;border:1px solid #e3e5ee}" +
    "#fz-f{display:flex;align-items:center;border-top:1px solid #e3e5ee}#fz-t{flex:1;border:0;padding:12px;font:inherit;outline:none;resize:none}" +
    "#fz-s{border:0;background:none;color:" + color + ";font-weight:700;padding:0 14px;cursor:pointer;align-self:stretch}" +
    "#fz-mic{border:0;background:none;font-size:20px;width:40px;height:40px;border-radius:50%;cursor:pointer;flex:none}" +
    "#fz-mic.fz-rec{background:#ef4444;animation:fzp 1s infinite}@keyframes fzp{50%{box-shadow:0 0 0 8px rgba(239,68,68,.25)}}" +
    "#fz-e{border:0;border-top:1px solid #e3e5ee;padding:8px 12px;font:inherit;outline:none}.fz-typing{color:#888;font-size:12px}";
  var s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
  var btn = document.createElement("button"); btn.id = "fz-btn"; btn.setAttribute("aria-label", "Discuter"); btn.textContent = "💬";
  var box = document.createElement("div"); box.id = "fz-box";
  box.innerHTML = '<div id="fz-h"><span><b></b><small>Assistant virtuel (IA)</small></span>' +
    (canSpeak ? '<button id="fz-v" type="button"></button>' : "") +
    '<button id="fz-x" type="button" aria-label="Fermer">✕</button></div><div id="fz-m"></div>' +
    '<input id="fz-e" type="email" placeholder="Votre e-mail (facultatif, pour vous recontacter)">' +
    '<form id="fz-f"><textarea id="fz-t" rows="1" placeholder="Votre message…"></textarea>' +
    (SR ? '<button id="fz-mic" type="button" aria-label="Parler" title="Parler (dictée faite par votre navigateur)">🎤</button>' : "") +
    '<button id="fz-s">Envoyer</button></form>';
  document.body.appendChild(btn); document.body.appendChild(box);
  var $ = function (id) { return box.querySelector("#" + id); };
  box.querySelector("#fz-h b").textContent = title;
  if (st.email) { $("fz-e").value = st.email; }
  function add(dir, text) {
    var d = document.createElement("div"); d.className = "fz-b " + (dir === "in" ? "fz-in" : "fz-out");
    String(text).split(/(https?:\/\/[^\s<>"]+)/).forEach(function (part, i) {  // liens cliquables (jamais de HTML)
      if (i % 2) {
        var url = part.replace(/[.,;:!?)]+$/, ""), a = document.createElement("a");
        a.href = url; a.textContent = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.style.color = "inherit";
        d.appendChild(a); if (url.length < part.length) d.appendChild(document.createTextNode(part.slice(url.length)));
      } else if (part) d.appendChild(document.createTextNode(part));
    });
    $("fz-m").appendChild(d); $("fz-m").scrollTop = 1e9;
  }
  if (!st.log.length) add("out", "Bonjour 👋 Je suis l'assistant virtuel (IA) de l'équipe. Comment puis-je vous aider ?" +
    (SR ? " Vous pouvez écrire, ou appuyer sur 🎤 pour me parler." : ""));
  st.log.forEach(function (m) { add(m.d, m.t); });

  // --- lecture à voix haute des réponses ---
  var unlocked = false, lastWasVoice = false;
  function stopSpeaking() { if (canSpeak) { try { speechSynthesis.cancel(); } catch (e) {} } }
  function unlockSpeech() {  // iPhone/iPad : la voix doit être « débloquée » par un geste (appui sur 🎤)
    if (!canSpeak || unlocked) return;
    unlocked = true;
    try { var u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); } catch (e) {}
  }
  function clean(t) {
    t = String(t).replace(/https?:\/\/\S+/g, "");
    try { t = t.replace(new RegExp("[\\p{Extended_Pictographic}\\uFE0F\\u200D]", "gu"), ""); } catch (e) {}
    return t.replace(/[*_#>`•|]/g, " ").replace(/\s+/g, " ").trim();
  }
  function pickVoice() {
    var vs = speechSynthesis.getVoices() || [], full = lang.toLowerCase().replace("_", "-"), p = full.slice(0, 2), best = null;
    for (var i = 0; i < vs.length; i++) {
      var l = (vs[i].lang || "").toLowerCase().replace("_", "-");
      if (l === full) return vs[i];
      if (!best && l.indexOf(p) === 0) best = vs[i];
    }
    return best;
  }
  function speak(t) {
    if (!canSpeak || !st.speak) return;
    var c = clean(t); if (!c) return;
    var u = new SpeechSynthesisUtterance(c), v = pickVoice();
    u.lang = lang; if (v) u.voice = v; u.rate = 1.02;
    speechSynthesis.speak(u);
  }
  function showSpeak() { if ($("fz-v")) { $("fz-v").textContent = st.speak ? "🔊" : "🔇"; $("fz-v").title = st.speak ? "Réponses lues à voix haute (couper)" : "Lire les réponses à voix haute"; } }
  if ($("fz-v")) { showSpeak(); $("fz-v").onclick = function () { st.speak = !st.speak; save(); showSpeak(); if (!st.speak) stopSpeaking(); else unlockSpeech(); }; }
  $("fz-x").onclick = function () { box.classList.remove("open"); stopSpeaking(); if (rec) rec.abort(); };

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
          if (m.direction === "out") {
            setTyping(false); waiting = false; add("out", m.content); st.log.push({d: "out", t: m.content});
            if (lastWasVoice) speak(m.content);
          }
        });
        save();
      }).catch(function () {});
  }
  var tick = 0;  // toutes les 2,5 s quand on attend une réponse, sinon toutes les 5 s si le chat est ouvert
  setInterval(function () { tick++; if (waiting || (box.classList.contains("open") && tick % 2 === 0)) poll(); }, 2500);
  btn.onclick = function () { box.classList.toggle("open"); if (box.classList.contains("open")) { track("chat_ouvert"); poll(); $("fz-t").focus(); } else stopSpeaking(); };
  $("fz-t").onkeydown = function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(false); } };
  $("fz-f").onsubmit = function (e) { e.preventDefault(); send(false); };

  function send(voice) {
    var t = $("fz-t").value.trim(); if (!t) return;
    st.email = $("fz-e").value.trim(); $("fz-t").value = "";
    lastWasVoice = !!voice;
    add("in", t); st.log.push({d: "in", t: t}); save(); track(voice ? "chat_vocal" : "chat_message");
    fetch(base + "/public/chat/send", {method: "POST", headers: {"Content-Type": "text/plain"},
      body: JSON.stringify({session: st.session, message: t, site: site, email: st.email, voice: !!voice})})
      .then(function (r) { if (r.status === 429) add("out", "Trop de messages pour le moment, réessayez un peu plus tard 🙏"); else { waiting = true; setTyping(true); } })
      .catch(function () { add("out", "Connexion impossible pour le moment, réessayez plus tard."); });
  }

  // --- dictée : appui sur 🎤, on parle, ça s'envoie tout seul à la fin de la phrase ---
  var rec = null;
  if (SR) $("fz-mic").onclick = function () {
    if (rec) { rec.stop(); return; }
    unlockSpeech(); stopSpeaking();
    var mic = $("fz-mic"), before = $("fz-t").value.trim(), heard = "";
    rec = new SR(); rec.lang = lang; rec.interimResults = true; rec.maxAlternatives = 1;
    rec.onresult = function (e) {
      heard = "";
      for (var i = 0; i < e.results.length; i++) heard += e.results[i][0].transcript;
      $("fz-t").value = (before ? before + " " : "") + heard.trim();
    };
    rec.onerror = function (e) {
      if (e.error === "not-allowed" || e.error === "service-not-allowed")
        add("out", "Le micro est bloqué : autorisez-le dans votre navigateur pour me parler, ou écrivez-moi 🙂");
    };
    rec.onend = function () { rec = null; mic.classList.remove("fz-rec"); if (heard.trim()) send(true); };
    try { rec.start(); mic.classList.add("fz-rec"); track("chat_micro"); } catch (e) { rec = null; }
  };
})();
