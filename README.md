# 🚀 Fusée — une équipe d'agents IA qui travaille pour toi 24h/24

Sept agents IA (Claude) avec chacun leur spécialité, qui discutent entre eux dans un **groupe façon WhatsApp**,
cherchent sur internet, écrivent du code, créent des jeux et te préparent des produits à vendre.
Tu suis tout depuis un **tableau de bord web** et tu peux leur écrire à tout moment.

| Agent | Rôle | Cycle |
|---|---|---|
| 🧭 **Atlas** | Directeur : fixe les priorités, répartit le travail, t'écrit des rapports avec les « Actions pour Patron » | 60 min |
| 📈 **Wolf** | Trader : suit les marchés, gère un **portefeuille simulé** (10 000 € fictifs) pour tester ses stratégies | 45 min |
| 💻 **Neo** | Développeur : code des produits vendables (scripts, bots, templates SaaS…) et les teste | 40 min |
| 🎮 **Pixel** | Créateur de jeux HTML5 originaux, jouables dans le navigateur (itch.io, portails web…) | 50 min |
| 🔭 **Scout** | Veille : nouveautés IA, tendances, niches, opportunités, affiliation | 60 min |
| 💰 **Mercure** | Ventes : où vendre, à quel prix, pages de vente, plan de lancement, conseils | 60 min |
| 📬 **Iris** | Service client : lit les e-mails des clients et leur répond, en te notifiant à chaque fois | dès qu'un mail arrive |

Chaque agent se réveille à son rythme **ou dès qu'on le mentionne** (`@Neo`, `@Tous`…).

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env      # puis mets ta clé ANTHROPIC_API_KEY dans .env
python main.py
```

Ouvre ensuite **http://localhost:8000**.

## Les faire tourner 24h/24 sur ton ordinateur

Les agents ont besoin que l'ordinateur reste **allumé et connecté à internet** (ils font leurs recherches
Google/web eux-mêmes).

- **Windows** : double-clique sur `start.bat`. Désactive la mise en veille
  (Paramètres → Système → Alimentation → Mise en veille : Jamais).
- **Mac / Linux** : `./start.sh` (sur Mac, il empêche aussi la mise en veille).
- **Serveur / VPS Linux** (le plus fiable, ~5 €/mois, tourne même ordi éteint) : voir `fusee.service`.

Ces scripts relancent Fusée automatiquement s'il plante.
Pour voir le tableau de bord depuis ton téléphone sur le même Wi-Fi : `http://<IP-de-ton-ordi>:8000`
(mets un `DASHBOARD_PASSWORD` dans `.env`). Hors de chez toi : installe [Tailscale](https://tailscale.com)
(gratuit) sur l'ordinateur et le téléphone, plutôt que d'ouvrir un port sur ta box.

## Ils proposent, tu valides ✅

Les agents imaginent et préparent des business tout seuls (recherche, code, jeux, pages de vente, stratégie
d'investissement…). Mais **avant de lancer quoi que ce soit** (publier, vendre, investir, dépenser), ils
t'envoient une **demande de validation** : quoi, pourquoi, combien ça coûte, ce que ça peut rapporter,
les risques et les étapes exactes. Tu reçois une notification sur ton téléphone et tu cliques
**Accepter** ou **Refuser** (avec un commentaire si tu veux) dans l'onglet ✅ Validations.
L'agent est réveillé avec ta réponse et continue.

## Notifications sur ton téléphone 📱

1. Installe l'app gratuite **ntfy** (Android / iPhone).
2. Abonne-toi à un sujet au nom secret (ex. `fusee-edouard-8f3k29x`).
3. Mets ce nom dans `.env` : `NTFY_TOPIC=fusee-edouard-8f3k29x`.
4. Onglet 🔔 Notifs → « Envoyer une notification de test ».

Tu es notifié pour : chaque demande de validation, chaque rapport, chaque réponse envoyée à un client,
et les alertes importantes des agents.

## Service client 📬 (quand un business commence à marcher)

Crée une adresse e-mail dédiée au business (ex. Gmail + « mot de passe d'application »), mets-la dans `.env`
(`IMAP_HOST`, `SMTP_HOST`, `EMAIL_USER`, `EMAIL_PASSWORD`). Iris lit les nouveaux e-mails toutes les 2 min
et répond aux clients. Dans l'onglet 📬 Clients, tu choisis le mode :
- **Réponse automatique + notification** : Iris répond tout de suite, tu reçois la question et la réponse sur ton téléphone ;
- **Je valide chaque réponse** : rien ne part sans ton clic.

Pour les remboursements, litiges ou cas délicats, Iris ne tranche jamais seule : elle te prévient.

## Le tableau de bord

- **Colonne de gauche** : chaque agent, son statut en direct, ce qu'il fait, son nombre de cycles et son coût.
- **Centre** : le groupe de discussion. Écris-leur ; sans mention, c'est Atlas qui répond.
- **Onglets à droite** :
  - 🤖 **Agent** : le journal détaillé de l'agent sélectionné (recherches web, fichiers écrits, réflexions) + sa mémoire/plan, et un bouton pour lancer un cycle tout de suite
  - 💡 **Idées** : le tableau des idées de business avec revenu estimé et statut
  - 📄 **Rapports** : les rapports d'Atlas pour toi (à lire le matin ☕)
  - 📈 **Portefeuille** : le paper trading de Wolf (P&L, ordres, justifications)
  - 📁 **Fichiers** : tout ce qu'ils ont produit (code, jeux jouables, fiches de vente)
  - ⚡ **Tout** : le flux d'activité de toute l'équipe
- **🎯 Consigne** : une consigne permanente lue par tous (ex. « priorité aux jeux et aux outils pour freelances »).
- **⏸️ Pause** : arrête tous les agents.

## Coûts — à lire

Chaque cycle d'agent est un appel payant à l'API Claude (en général quelques centimes à quelques dizaines
de centimes selon le travail fait). Avec les réglages par défaut, l'équipe peut faire ~150 cycles/jour.
Le garde-fou **`DAILY_BUDGET_USD`** (10 $ par défaut) arrête tout dès que le plafond du jour est atteint.
Pour dépenser moins : `INTERVAL_MULTIPLIER=3` (cycles 3× plus espacés), `FUSEE_EFFORT=low`, ou un modèle
moins cher (`FUSEE_MODEL=claude-sonnet-5-5`). Le coût s'affiche en direct en haut du tableau de bord.

## Ce qu'ils peuvent et ne peuvent pas faire (volontairement)

✅ Chercher et lire sur internet, écrire et exécuter du code Python dans `workspace/`, créer des jeux,
préparer des produits et des pages de vente, analyser les marchés, se coordonner, t'écrire des rapports.

❌ Ils **ne touchent pas à ton argent** : pas d'ordre de bourse réel, pas d'achat, pas de création de compte,
pas de publication en ton nom. Quand quelque chose demande ça (mettre un jeu en vente sur itch.io, ouvrir un
compte Gumroad, investir), ils te demandent ton accord et te donnent les étapes : **c'est toi qui valides
et cliques**. Seule exception, que tu actives toi-même : les réponses aux e-mails clients. Ça évite qu'une erreur ou une page web piégée vide ton compte pendant que tu dors.

⚠️ **Aucun revenu n'est garanti.** Les agents produisent des produits, des idées et des analyses ; l'argent
vient quand tu publies et vends ce qui est bon. Les recommandations de trading ne sont pas des conseils
financiers : ne mets en réel qu'une stratégie qui a fait ses preuves en simulation, et que de l'argent que tu
peux perdre. Si tu vends, pense à déclarer tes revenus (ex. micro-entreprise en France).

## Personnaliser

- Ajouter / modifier un agent : `fusee_agents/agents.py` (nom, rôle, outils, rythme).
- Ajouter un outil : `fusee_agents/tools.py`.
- `ALLOW_CODE_EXEC=false` dans `.env` empêche les agents d'exécuter du code (ils peuvent toujours en écrire).

## Structure

```
main.py                     lancement (serveur web + agents)
start.sh / start.bat        lancement 24h/24 avec redémarrage auto
fusee.service               service pour serveur Linux
fusee_agents/
  agents.py                 l'équipe et leurs instructions
  runner.py                 un cycle de travail d'un agent (boucle Claude + outils)
  scheduler.py              rythme 24h/24, réveil sur mention, limite de parallélisme
  tools.py                  outils : chat, mémoire, fichiers, Python, idées, rapports, validations, paper trading, clients
  notify.py                 notifications téléphone (ntfy)
  mailbox.py                e-mails clients (IMAP/SMTP)
  db.py                     base SQLite (data/fusee.db)
  web.py, static/index.html tableau de bord
workspace/                  tout ce que les agents produisent
```
