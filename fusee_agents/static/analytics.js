/* Statistiques Fusée (sans cookies) — à inclure sur un site :
   <script src="https://ADRESSE-PUBLIQUE/public/a.js" data-site="nom-du-site"></script>
   Compte les visites, les clics sur les boutons d'achat (liens Stripe ou éléments data-buy) et les contacts. */
(function () {
  if (window.__fuseeA) return; window.__fuseeA = true;
  var me = document.currentScript, base = me.src.replace(/\/public\/(a|chat)\.js.*$/, "");
  var site = me.getAttribute("data-site") || location.hostname;
  var vid;
  try { vid = sessionStorage.getItem("fz_v"); if (!vid) { vid = Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem("fz_v", vid); } }
  catch (e) { vid = Math.random().toString(36).slice(2); }
  var p = new URLSearchParams(location.search), utm = p.get("utm_source") || p.get("ref") || "";
  var ref = ""; try { ref = document.referrer ? new URL(document.referrer).hostname : ""; if (ref === location.hostname) ref = ""; } catch (e) {}
  var device = window.innerWidth < 768 ? "mobile" : "ordi";
  function send(ev) {
    var body = JSON.stringify({site: site, path: location.pathname, event: ev, visitor: vid, ref: ref, utm: utm, device: device});
    try { if (navigator.sendBeacon && navigator.sendBeacon(base + "/public/t", new Blob([body], {type: "text/plain"}))) return; } catch (e) {}
    fetch(base + "/public/t", {method: "POST", body: body, headers: {"Content-Type": "text/plain"}, keepalive: true}).catch(function () {});
  }
  window.fuseeTrack = send;
  send("vue");
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a,button,[data-buy]");
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (a.hasAttribute("data-buy") || /buy\.stripe\.com|checkout\.stripe\.com|gumroad\.com|lemonsqueezy|itch\.io\/.+\/purchase/.test(href)) send("clic_achat");
    else if (/^mailto:|^tel:/.test(href)) send("clic_contact");
  }, true);
})();
