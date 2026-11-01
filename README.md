# 🚀 Fusée — ton équipe d'agents IA qui travaille 24h/24

Quatorze agents IA (Claude), chacun avec un **type** et un métier. Ils discutent entre eux dans un **groupe
façon WhatsApp**, cherchent sur internet, créent des **sites, des applis, des jeux, des pubs et des vidéos**, te
les **montrent (captures, vidéos, liens)**, les **mettent en ligne et en vente quand tu valides**, puis **parlent
avec les clients** et te disent **qui est intéressé, par quoi, et s'il vaut le coup pour le futur**.

Tout se suit depuis **l'application Fusée**, installable sur ton téléphone et ton ordinateur.

### Les 9 types d'agents

| Type | Agent | Ce qu'il fait |
|---|---|---|
| 🧭 **Orchestrateur** | Atlas | Fixe le cap (1-2 projets), découpe le travail, lance les workflows, rapports |
| 🔀 **Routeur** | Nexus | Reçoit tes messages sans @mention et les aiguille vers le bon agent |
| ⛓️ **Séquentiel** | Relais | Chaînes d'étapes : chaque agent reçoit le résultat du précédent (ex. Scout → Victor → Neo → Mercure) |
| 🐙 **Parallèle** | Hydre | Fait travailler plusieurs agents en même temps, puis fusionne et compare leurs résultats |
| 🙋 **Humain** | Clara | Le pont avec toi : te pose les questions, prépare ta liste « À faire » pas à pas, te relance |
| 🛠️ **Outil** | Forge | Fabrique la boîte à outils de l'équipe (scripts testés que tous les agents utilisent) |
| 📚 **Compétence** | Sage | Écrit les fiches de savoir-faire (comment lancer un site, fixer un prix…) que les agents lisent |
| 📣 **Marketing** | Mercure | Pubs, visuels, vidéos TikTok/Reels/Shorts, contenus, référencement |
| 🤝 **Commercial** | Victor | Offres pour particuliers et entreprises, prix, devis, liens de paiement, conclure les ventes |

### Les spécialistes

| Agent | Métier |
|---|---|
| 💻 **Neo** | Sites, applis web, logiciels vendables ; captures puis mise en ligne |
| 🎮 **Pixel** | Jeux originaux jouables dans le navigateur |
| 🔭 **Scout** | Veille : tendances, nouveautés, opportunités |
| 📬 **Iris** | Relation clients : chat des sites et e-mails, évaluation de chaque prospect |
| 📈 **Wolf** | Ta **stratégie d'investissement personnalisée**, et un portefeuille simulé pour tester |

Les agents de coordination (routeur, séquentiel, parallèle, relation clients) travaillent **seulement quand on a
besoin d'eux** : ils ne coûtent rien le reste du temps.

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

## Ce qui rend l'équipe efficace

- **📦 Catalogue produits** : chaque produit (site, appli, jeu, template, service) avec son prix, son site, ses
  liens de paiement, ses visiteurs, ses ventes et son chiffre d'affaires. Les agents décident avec ces chiffres.
- **💶 Ventes détectées en temps réel** : toutes les 3 minutes, Fusée lit les paiements Stripe, les attribue au bon
  produit, enregistre le client et t'envoie « 💶 Vente ! » sur ton téléphone. (À la première connexion, l'historique
  est importé sans notification.)
- **📊 Statistiques des sites, sans cookies** : visites, provenance (Google, TikTok… grâce aux liens `?utm_source=`),
  ordinateur/mobile, clics sur « Acheter », chats ouverts, taux de conversion. Le widget de chat les charge tout
  seul ; sinon `<script src="PUBLIC_URL/public/a.js" data-site="nom-du-site"></script>`. Les visites des agents
  eux-mêmes (captures, audits) ne comptent pas.
- **🔍 Audit qualité obligatoire** : avant toute mise en ligne, Fusée ouvre le site comme un visiteur (ordinateur et
  mobile) et vérifie erreurs JavaScript, liens cassés, débordement sur mobile, titre et description Google, aperçu de
  partage, contact, mentions légales, prix affiché, statistiques, poids et vitesse. Un site bâclé est **bloqué**
  avec la liste précise de ce qu'il faut corriger.
- **🧠 Mémoire collective** : les agents enregistrent ce qu'ils apprennent (prix acceptés, canaux qui marchent,
  erreurs à éviter) et le retrouvent par recherche, même des semaines plus tard. Les souvenirs utiles sont
  rappelés automatiquement à chaque cycle.
- **🔒 Tes clés restent secrètes** : le code écrit par les agents tourne sans aucune clé ni mot de passe de ton
  `.env` (API, Stripe, e-mail, notifications).

## Les spécialistes sont équipés

- **📈 Wolf — vraies données de bourse** : prix, tendances, moyennes, RSI, volatilité, pire baisse de n'importe quel
  actif (actions, ETF, indices, crypto : `AAPL`, `CW8.PA`, `^FCHI`, `BTC-EUR`…), et **backtests** qui rejouent une
  stratégie (achat-conservation, croisement de moyennes, RSI, investissement mensuel) sur des années d'historique
  réel, comparée à un simple achat-conservation. Le portefeuille simulé utilise **toujours le prix réel** (impossible
  d'inventer un prix) et se met à jour chaque heure.
- **💻 Neo — sites pro en quelques secondes** : deux modèles (« produit » = page de vente, « vitrine » = site de
  commerce ou d'artisan) avec design moderne, version mobile, référencement, **image d'aperçu générée** pour les
  partages, mentions légales, contact, statistiques et bouton d'achat — ils obtiennent 100/100 à l'audit dès le
  départ. Et des **tests automatiques** dans un vrai navigateur (remplir, cliquer, vérifier le résultat, sur
  ordinateur et mobile) pour ses applis et les jeux de Pixel.
- **📣 Mercure — calendrier de contenus** : des publications **prêtes à poster** (accroche, texte avec hashtags,
  vidéo ou image, lien suivi). Dans l'onglet 📅 Contenus, tu copies, tu télécharges, tu postes, tu cliques
  « J'ai posté » — et Mercure voit combien de visiteurs chaque publication a apportés.

## Installation sur ton Mac (iMac / Mac mini)

1. Installe **Python 3.12** depuis https://www.python.org/downloads/macos/ (le paquet `.pkg`, puis double-clic sur
   « Install Certificates.command » dans le dossier Python des Applications).
2. Télécharge ce projet (bouton vert **Code → Download ZIP** sur GitHub), dézippe-le dans ton dossier personnel.
3. Ouvre le **Terminal**, tape `cd ` (avec un espace), glisse le dossier Fusee dans la fenêtre, appuie sur Entrée, puis :
   ```bash
   ./start.sh
   ```
   La première fois, il installe tout tout seul (quelques minutes), puis **ouvre l'application sur l'assistant de
   démarrage 🚀** : colle ta clé API (avec un parent), règle les notifications, et c'est parti.
4. Pour que Fusée **démarre tout seul** à chaque allumage et tourne jour et nuit :
   ```bash
   ./install-mac.sh
   ```
   Puis, dans **Réglages Système → Énergie**, active « Empêcher la suspension automatique lorsque l'écran est
   éteint » et « Démarrer automatiquement après une panne de courant ». (Pour désinstaller : `./install-mac.sh --remove`.)

Sur Windows : `start.bat`. Sur un serveur Linux : `fusee.service`.

### 🚀 L'assistant de démarrage

Au premier lancement, l'appli s'ouvre dessus (et il reste dans l'onglet 🚀 Démarrage). Pour chaque service — clé API,
notifications, mot de passe, profil et plan IA, Netlify, Stripe, adresse publique, e-mail — il explique quoi faire,
enregistre la valeur dans `.env` (fichier lisible seulement par toi), et un bouton **🧪 Tester** vérifie que la
connexion marche. Les clés ne sont jamais réaffichées en clair. Sans mot de passe d'appli, les réglages ne
peuvent être modifiés que depuis le Mac lui-même. Un bouton redémarre Fusée pour appliquer les changements.

### 📲 Installer l'application

- **Ordinateur** (Chrome/Edge) : bouton « 📲 Installer l'app » en haut, ou l'icône dans la barre d'adresse.
- **Téléphone, même Wi-Fi** : ouvre `http://<IP-de-ton-Mac>:8000` puis Safari → Partager → « Sur l'écran
  d'accueil » (ou Chrome Android → ⋮ → « Installer l'application »).
- **Téléphone, hors de chez toi** : installe [Tailscale](https://tailscale.com) (gratuit) sur le Mac et le
  téléphone, puis ouvre `http://<nom-du-mac>:8000`.

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
- **💬 Groupe** : leur discussion, avec les captures, vidéos et liens. Écris-leur (`@Neo`, `@Tous`…) ; sans mention, Nexus aiguille ta demande.
- **📋 Suivi** :
  - 🙋 **Pour toi** : les questions de l'équipe (boutons de réponse) et ta liste « À faire » pas à pas
  - 📅 **Contenus** : les publications prêtes à poster (copier, télécharger, « J'ai posté »)
  - 📦 **Produits** : le catalogue avec ventes, chiffre d'affaires, visiteurs et conversion ; clique un produit pour
    voir d'où viennent ses visiteurs, jour par jour
  - ✅ **Validations** : leurs demandes (avec captures) → Accepter / Refuser
  - 👥 **Prospects** : chaque personne, son intérêt, son ressenti, son score, la conversation complète, et tu peux lui répondre
  - 🖼️ **Vitrine** : aperçu de tous les sites, applis et jeux (local et en ligne), galerie des pubs et vidéos
  - 💰 **Argent** : budget, dépenses, revenus, ventes Stripe, profil investisseur et stratégie
  - ⛓️ **Workflows** : les chaînes séquentielles et les travaux parallèles, étape par étape
  - 🧰 **Boîte** : les outils de Forge et les fiches de compétences de Sage
  - 💡 Idées · 📄 Rapports · 📈 Bourse (simulée) · 🔔 Notifs · ⚙️ Réglages · ⚡ Tout

## Budget et coûts 💰

Fusée suit ton **argent réel** (onglet 💰 Argent) : budget de départ (100 € par défaut), dépenses d'IA, autres
dépenses que tu as validées, revenus (Stripe + ce que tu ajoutes), et ce qu'il reste.

- **La part IA** (50 € par défaut) est **étalée sur un nombre de jours** (30 par défaut, soit ~1,67 €/jour) :
  quand la part du jour est dépensée, les agents se reposent jusqu'au lendemain. Quand la part IA totale est
  épuisée, ils s'arrêtent. Tout se règle dans l'appli.
- **Les dépenses réelles** proposées par les agents (pub, nom de domaine…) sont refusées d'office si elles
  dépassent l'argent disponible ; une fois validées, elles sont déduites automatiquement.
- **Le plan de modèles** (`FUSEE_PLAN` dans `.env`) fixe la qualité et le coût :
  - `eco` : orchestrateur Sonnet, tous les autres Haiku (le moins cher, idéal pour démarrer avec 100 €) ;
  - `equilibre` : orchestrateur Opus, agents de travail Sonnet, coordination Haiku ;
  - `max` : Opus partout (le plus intelligent, beaucoup plus cher).
- Le chat public des sites est limité (20 messages/h par visiteur, 400/h au total) pour protéger le budget.

## Ta stratégie d'investissement 📈

Dans l'onglet 💰 Argent, remplis ton **profil investisseur** (âge, objectif, horizon, rapport au risque…) :
Wolf rédige ta **stratégie personnalisée** et la tient à jour. Une première version est dans `STRATEGIE.md`.
Wolf ne passe jamais d'ordre réel : tout investissement réel passe par ta validation, et c'est toi qui le fais.

## Si tu as moins de 18 ans

Mets `OWNER_MINOR=true` dans `.env` : les agents en tiennent compte (pas de bourse ni de crypto, démarches
préparées avec un parent). La clé API Anthropic, Stripe et les plateformes de vente demandent d'avoir 18 ans :
**un parent ouvre ces comptes à son nom** et reçoit l'argent. Avant de vendre régulièrement, vérifiez ensemble le
cadre (statut, déclaration des revenus) sur service-public.fr.

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
install-mac.sh                 démarrage automatique sur Mac (service launchd)
fusee.service                  service pour serveur Linux
fusee_agents/
  agents.py                    l'équipe et leurs instructions
  runner.py                    un cycle de travail d'un agent (boucle Claude + outils)
  scheduler.py                 rythme 24h/24, réveil sur mention / message client
  tools.py                     tous les outils des agents
  workflow.py                  moteur des workflows séquentiels et parallèles
  budget.py                    budget réel en euros, plafonds IA
  sales.py                     détection des ventes Stripe en temps réel
  analytics.py                 statistiques des sites (sans cookies)
  markets.py                   données de bourse réelles, indicateurs, backtests
  sites.py, templates/         sites pro à partir de modèles
  setup.py                     assistant de démarrage (.env, tests des connexions)
  browser.py                   navigateur : captures, navigation, vidéos
  integrations.py              Netlify (mise en ligne) et Stripe (paiements, ventes)
  mailbox.py                   e-mails clients (IMAP/SMTP)
  notify.py                    notifications téléphone (ntfy)
  db.py                        base SQLite (data/fusee.db)
  web.py                       serveur de l'appli + chat public des sites
  static/                      l'application (PWA), le widget de chat, les icônes
workspace/                     tout ce que les agents produisent (sites/, jeux/, pubs/, captures/…)
```
