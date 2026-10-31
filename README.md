# 🚀 Fusée — une équipe d'agents IA qui travaille pour toi 24h/24

Six agents IA (Claude) avec chacun leur spécialité, qui discutent entre eux dans un **groupe façon WhatsApp**,
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

Chaque agent se réveille à son rythme **ou dès qu'on le mentionne** (`@Neo`, `@Tous`…).

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env      # puis mets ta clé ANTHROPIC_API_KEY dans .env
python main.py
```

Ouvre ensuite **http://localhost:8000**.

Pour qu'ils tournent vraiment jour et nuit, l'ordinateur (ou un petit serveur/VPS) doit rester allumé
avec `python main.py` lancé (par exemple dans `tmux`, ou en service systemd).

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
compte Gumroad, investir), ils te le préparent et te le listent dans les rapports : **c'est toi qui valides
et cliques**. Ça évite qu'une erreur ou une page web piégée vide ton compte pendant que tu dors.

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
fusee_agents/
  agents.py                 l'équipe et leurs instructions
  runner.py                 un cycle de travail d'un agent (boucle Claude + outils)
  scheduler.py              rythme 24h/24, réveil sur mention, limite de parallélisme
  tools.py                  outils : chat, mémoire, fichiers, Python, idées, rapports, paper trading
  db.py                     base SQLite (data/fusee.db)
  web.py, static/index.html tableau de bord
workspace/                  tout ce que les agents produisent
```
