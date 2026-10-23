# Mettre Escadron Phénix sur itch.io

## Ce qu'il y a dans ce dossier

- `escadron-phenix-itch.zip` : le jeu à envoyer (`index.html` + `three.min.js`). N'ouvre pas ce zip, envoie-le tel quel.
- `couverture-630x500.png` : l'image de couverture.
- `captures/` : les captures d'écran pour la page.

## Étapes

1. Sur itch.io, clique sur **« Upload new project »**.
2. **Title** : `Escadron Phénix`
3. **Short description or tagline** : `Combat aérien 3D gratuit : 6 missions, dogfights, missiles et le terrible Baron Rouge.`
4. **Kind of project** : **HTML**.
5. **Uploads** : envoie `escadron-phenix-itch.zip` et coche **« This file will be played in the browser »**.
6. **Embed options** :
   - Viewport dimensions : **1280 × 720**
   - Coche **« Mobile friendly »** (orientation : **Landscape**) et **« Fullscreen button »**.
7. **Pricing** : **« No payment required »**, puis active **« Suggested donation »** à **2 €**.
8. **Cover image** : `couverture-630x500.png`.
9. **Screenshots** : dans cet ordre : 06, 04, 03, 05, 07, 08, 01.
10. **Genre** : Action. **Tags** : `flight`, `combat`, `airplanes`, `3d`, `arcade`, `webgl`, `browser`, `french`, `singleplayer`, `shooter`.
11. **AI disclosure** : itch.io demande si le jeu a été fait avec de l'IA générative. Réponds honnêtement **oui** : le code a été écrit avec l'aide d'une IA.
12. **Description** : copie le texte plus bas, puis clique sur **Save** et passe la page en **Public**.

## Après la publication

Mets l'adresse de ta page dans le jeu : dans `escadron/index.html`, remplace `const SUPPORT_URL = '';` par `const SUPPORT_URL = 'https://ton-pseudo.itch.io/escadron-phenix';`. Le bouton « Soutiens le créateur » apparaîtra à la fin des missions. Refais ensuite le zip et renvoie-le.

Pour les dons, c'est comme pour Fusée Kármán : un parent doit t'aider pour le compte de paiement.

---

## Description à copier (français)

**Prends les commandes d'un avion de chasse et défends l'archipel !**

Pilote de l'escadron Phénix, tu affrontes l'escadrille Corbeau au-dessus d'îles tropicales, de l'aube au coucher du soleil.

- **6 missions** : entraînement, interception, destruction de radars, protection d'un convoi, attaque d'une flotte avec porte-avions, et le duel final contre le **Baron Rouge**.
- **Combat libre** : des vagues d'ennemis sans fin. Jusqu'où iras-tu ?
- Canon, **missiles à verrouillage** et **leurres** pour échapper aux missiles ennemis.
- Un **ailier** qui combat avec toi et un contrôle radio en français.
- **3 avions** et **5 peintures** à débloquer avec les étoiles.
- 3 vues : poursuite, cockpit et **vue cinéma** (parfaite pour les vidéos).
- 12 succès, 3 niveaux de difficulté et une aide au pilotage pour débuter.
- Marche sur ordinateur, à la manette et sur téléphone.

**Commandes** : flèches ou ZQSD pour piloter, Espace pour le canon, F pour un missile, L pour les leurres, Maj pour la postcombustion, C pour changer de vue.

## Description to copy (English)

**Take the controls of a fighter jet and defend the islands!**

As a pilot of Phoenix Squadron, you face the Raven squadron over tropical islands, from dawn to sunset.

- **6 missions**: training, interception, radar strike, convoy escort, an attack on a carrier fleet, and the final duel against the **Red Baron**.
- **Free combat**: endless enemy waves. How far can you go?
- Gun, **lock-on missiles** and **flares** to dodge enemy missiles.
- A **wingman** who fights at your side, and radio chatter (in French).
- **3 jets** and **5 paint schemes** to unlock with stars.
- 3 views: chase, cockpit and **cinematic camera** (great for videos).
- 12 achievements, 3 difficulty levels and flight assist for beginners.
- Plays on desktop, with a gamepad, and on mobile.

**Controls**: arrow keys or WASD to fly, Space for the gun, F for a missile, L for flares, Shift for afterburner, C to switch views.
