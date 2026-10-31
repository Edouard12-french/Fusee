# 🚀 Fusée — ton équipe d'agents IA qui travaille 24h/24

Huit agents IA (Claude) avec chacun leur métier. Ils discutent entre eux dans un **groupe façon WhatsApp**,
cherchent sur internet, créent des **sites, des applis, des jeux, des pubs et des vidéos**, te les **montrent
(captures, vidéos, liens)**, les **mettent en ligne et en vente quand tu valides**, puis **parlent avec les
clients** intéressés et te disent **qui est intéressé, par quoi, et s'il vaut le coup pour le futur**.

Tout se suit depuis **l'application Fusée**, installable sur ton téléphone et ton ordinateur.

| Agent | Métier |
|---|---|
| 🧭 **Atlas** | Directeur : priorités, répartition du travail, rapports pour toi (ventes, prospects, actions à faire) |
| 💻 **Neo** | Développeur : sites, applis web, logiciels vendables ; les montre en captures puis les met en ligne |
| 🎮 **Pixel** | Jeux originaux jouables dans le navigateur, avec captures et vidéos de gameplay |
| 💰 **Mercure** | Ventes aux **particuliers** + **pubs** (visuels) et **vidéos** (TikTok/Reels/Shorts) |
| 🏢 **Victor** | Ventes aux **entreprises** : offres B2B, pages pro, devis, plaquettes |
| 📬 **Iris** | Relation clients : répond sur le **chat des sites** et par e-mail, évalue chaque prospect |
| 🔭 **Scout** | Veille : tendances, nouveautés, niches, opportunités |
| 📈 **Wolf** | Marchés : stratégies testées sur un **portefeuille simulé** avant tout argent réel |

## Comment ça marche

1. **Ils créent** : un agent a une idée (ou tu lui en donnes une), il la construit — site, appli, jeu,
   page de vente, pub, vidéo — et te la **montre dans le groupe** avec captures d'écran, vidéo et liens.
2. **Tu valides** : avant toute mise en ligne, vente, dépense ou investissement, il t'envoie une
   **demande de validation** (avec les captures) → notification sur ton téléphone → **Accepter / Refuser**.
3. **Ils lancent** : après ton accord, le site est **mis en ligne** (lien public) et un **lien de paiement**
   est créé ; l'argent arrive sur **ton** compte Stripe. Les pubs et vidéos sont prêtes, c'est toi qui les postes.
4. **Ils vendent** : les visiteurs parlent à Iris sur le chat du site. Tu vois **chaque conversation**,
   et pour chaque personne : **particulier ou entreprise, ce qui l'intéresse, son ressenti 😍🙂😐🤔😠,
   un score sur 100 et son potentiel pour le futur**. Les prospects chauds (≥ 70) te sont notifiés.
   Tu peux aussi répondre toi-même à un client depuis l'appli.

## Installation

1. Installe [Python 3.11+](https://www.python.org/downloads/) (sur Windows, coche « Add Python to PATH »).
2. Télécharge ce projet, puis dans le dossier : copie `.env.example` en `.env` et mets au minimum ta clé
   `ANTHROPIC_API_KEY` (sur [platform.claude.com](https://platform.claude.com)) et un `DASHBOARD_PASSWORD`.
3. Lance :
   - **Windows** : double-clic sur `start.bat`
   - **Mac / Linux** : `./start.sh`

   Le script installe tout (y compris le navigateur des agents) et **ouvre l'application**.
   Il redémarre tout seul en cas de plantage.

### 📲 Installer l'application

- **Ordinateur** (Chrome/Edge) : bouton « 📲 Installer l'app » en haut, ou l'icône dans la barre d'adresse.
- **Téléphone, même Wi-Fi** : ouvre `http://<IP-de-ton-ordi>:8000` puis Chrome (Android) → ⋮ → « Installer
  l'application », ou Safari (iPhone) → Partager → « Sur l'écran d'accueil ».
- **Téléphone, hors de chez toi** : installe [Tailscale](https://tailscale.com) (gratuit) sur l'ordinateur et le
  téléphone, puis ouvre `http://<nom-de-ton-ordi>:8000`.

### 24h/24

L'ordinateur doit rester **allumé et connecté**. Désactive la mise en veille (Windows : Paramètres → Système →
Alimentation → Jamais ; sur Mac, `start.sh` l'empêche tout seul). Le plus fiable : un petit serveur (VPS,
~5 €/mois) avec `fusee.service`.

## Brancher les fonctions (fichier `.env`, puis redémarrer)

L'onglet **⚙️ Réglages** de l'appli montre ce qui est branché.

| Fonction | Ce qu'il faut | Coût |
|---|---|---|
| 📱 Notifications téléphone | App **ntfy** + un nom secret dans `NTFY_TOPIC` | gratuit |
| 🌍 Mise en ligne des sites | Compte [Netlify](https://netlify.com) + `NETLIFY_TOKEN` | gratuit pour démarrer |
| 💳 Paiements | Compte [Stripe](https://stripe.com) + `STRIPE_SECRET_KEY` (essaie d'abord avec une clé `sk_test_`) | commission Stripe par vente |
| 💬 Chat en direct sur les sites | Une adresse publique pour Fusée dans `PUBLIC_URL` (ci-dessous) | gratuit |
| ✉️ E-mails clients | Une adresse dédiée (ex. Gmail + mot de passe d'application) : `IMAP_HOST`, `SMTP_HOST`, `EMAIL_USER`, `EMAIL_PASSWORD` | gratuit |
| 🌐 Navigateur des agents | Bouton **🌐 Navigateur** dans l'appli (tu l'autorises ou le bloques quand tu veux) | — |

**Adresse publique pour le chat** : les sites en ligne doivent pouvoir joindre Fusée sur ton ordinateur.
Le plus simple : [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) (`tailscale funnel 8000`) qui donne
une adresse fixe du type `https://ton-ordi.tailXXXX.ts.net` → mets-la dans `PUBLIC_URL`. Seul le chat
(`/public/...`) est accessible sans mot de passe ; le reste de l'appli est protégé par `DASHBOARD_PASSWORD`.
Sans adresse publique, les sites affichent un contact par e-mail à la place.

## L'application

- **🤖 Équipe** : chaque agent, en direct : statut, ce qu'il fait, coût. Clique pour voir tout ce qu'il a fait et son plan.
- **💬 Groupe** : leur discussion, avec les captures, vidéos et liens. Écris-leur (`@Neo`, `@Tous`…).
- **📋 Suivi** :
  - ✅ **Validations** : leurs demandes (avec captures) → Accepter / Refuser
  - 👥 **Prospects** : chaque personne, son intérêt, son ressenti, son score, la conversation complète, et tu peux lui répondre
  - 🖼️ **Vitrine** : aperçu de tous les sites, applis et jeux (local et en ligne), galerie des pubs et vidéos
  - 💶 **Ventes** : argent réellement encaissé (Stripe), liens de paiement, sites en ligne
  - 💡 Idées · 📄 Rapports · 📈 Bourse (simulée) · 🔔 Notifs · ⚙️ Réglages · ⚡ Tout

## Coûts

Chaque cycle d'agent est un appel payant à l'API Claude. Le plafond **`DAILY_BUDGET_USD`** (10 $ par défaut)
arrête tout dès qu'il est atteint ; la dépense s'affiche en haut de l'appli. Pour dépenser moins :
`INTERVAL_MULTIPLIER=3`, `FUSEE_EFFORT=low` ou `FUSEE_MODEL=claude-sonnet-5-5`.
Le chat public est limité (20 messages/h par visiteur, 400/h au total) pour éviter qu'un abus ne vide le budget.

## Ce qu'ils font seuls, et ce qui reste à toi

✅ **Seuls** : recherche sur internet, sites, applis, jeux, pubs, vidéos, code ; captures et liens pour te
montrer ; réponses aux clients (avec notification, ou après ta validation si tu choisis ce mode).

✅ **Après ton accord** : mise en ligne des sites, création des liens de paiement.

👤 **Toi** : créer les comptes (Netlify, Stripe, réseaux sociaux…), poster les pubs/vidéos sur les réseaux et
payer d'éventuelles campagnes, investir de l'argent réel. Les agents te préparent tout, prêt à copier-coller.
C'est voulu : pendant que tu dors, ni une erreur de l'IA ni un site piégé ne peuvent dépenser ton argent,
publier en ton nom ou enfreindre les règles des plateformes.

⚠️ **Aucun revenu n'est garanti** : les agents produisent et vendent, le marché décide. Les vidéos sont des
animations générées par le code (texte, couleurs, captures du produit), pas des vidéos filmées. Les conseils
de bourse ne sont pas des conseils financiers. Dès que tu vends, il te faut un statut (ex. micro-entreprise),
des mentions légales/CGV sur les sites et la déclaration de tes revenus.

## Structure

```
main.py                        lancement (serveur + agents), ouvre l'appli
start.sh / start.bat           lancement 24h/24 avec installation et redémarrage auto
fusee.service                  service pour serveur Linux
fusee_agents/
  agents.py                    l'équipe et leurs instructions
  runner.py                    un cycle de travail d'un agent (boucle Claude + outils)
  scheduler.py                 rythme 24h/24, réveil sur mention / message client
  tools.py                     tous les outils des agents
  browser.py                   navigateur : captures, navigation, vidéos
  integrations.py              Netlify (mise en ligne) et Stripe (paiements, ventes)
  mailbox.py                   e-mails clients (IMAP/SMTP)
  notify.py                    notifications téléphone (ntfy)
  db.py                        base SQLite (data/fusee.db)
  web.py                       serveur de l'appli + chat public des sites
  static/                      l'application (PWA), le widget de chat, les icônes
workspace/                     tout ce que les agents produisent (sites/, jeux/, pubs/, captures/…)
```
