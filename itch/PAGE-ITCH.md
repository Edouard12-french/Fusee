# Mettre Fusée Kármán sur itch.io

## Avant de commencer

- Pour **recevoir de l'argent**, itch.io demande un compte PayPal ou un compte bancaire, et il faut être majeur. **Demande à un parent** de créer le compte de paiement avec toi.
- Tout ce qu'il faut est dans ce dossier :
  - `fusee-karman-itch.zip` : le jeu à envoyer (`index.html` + `three.min.js`).
  - `couverture-630x500.png` : l'image de couverture.
  - `captures/` : les captures d'écran à mettre sur la page.

## Étapes

1. Va sur itch.io, connecte-toi, puis clique sur **« Upload new project »**.
2. **Title** : `Fusée Kármán`
3. **Short description or tagline** : `De la Terre à la Lune en 3D : décolle d'une vraie base, amarre-toi à l'ISS et pose-toi sur la Lune.`
4. **Kind of project** : **HTML**.
5. **Uploads** : envoie `fusee-karman-itch.zip` et coche **« This file will be played in the browser »**.
6. **Embed options** :
   - Viewport dimensions : **1280 × 720**
   - Coche **« Mobile friendly »** et **« Fullscreen button »**.
7. **Pricing** : choisis **« No payment required »**, puis active **« Suggested donation »** avec **2 €**. Un jeu gratuit attire beaucoup plus de joueurs, et ceux qui l'aiment donnent quand même.
8. **Cover image** : `couverture-630x500.png`.
9. **Screenshots** : ajoute les images de `captures/` dans cet ordre : 02, 04, 06, 09, 10, 07, 03, 05, 08, 01. Les plus belles d'abord.
10. **Genre** : Simulation. **Tags** : `space`, `rocket`, `moon`, `3d`, `simulation`, `arcade`, `webgl`, `french`, `browser`, `singleplayer`.
11. **Description** : copie le texte plus bas (le français puis l'anglais, pour attirer aussi les joueurs étrangers).
12. Clique sur **Save**, puis passe la page en **Public** quand tout est prêt.

## Après la publication

Copie l'adresse de ta page (par exemple `https://ton-pseudo.itch.io/fusee-karman`) et mets-la dans le jeu : dans `jeu/index.html`, remplace

```js
const SUPPORT_URL = '';
```

par

```js
const SUPPORT_URL = 'https://ton-pseudo.itch.io/fusee-karman';
```

Le bouton « Soutenir le jeu » apparaîtra alors après l'alunissage, et le lien sera ajouté quand un joueur copie son score. Refais ensuite le zip et renvoie-le sur itch.io.

## Pour avoir des joueurs

- Participe à une **game jam** sur itch.io (onglet « Jams ») : c'est le meilleur moyen d'être vu.
- Publie une courte vidéo du décollage et de l'alunissage (TikTok, YouTube Shorts) avec le lien.
- Mets à jour le jeu de temps en temps : itch.io montre les jeux récemment mis à jour.

---

## Description à copier (français)

**Pilote une vraie fusée de la Terre jusqu'à la Lune !**

Choisis ta base de lancement et ton lanceur :
- **Kourou** (Guyane) avec **Ariane 6**
- **Cap Canaveral** (Floride) avec **Falcon 9**
- **Baïkonour** (Kazakhstan) avec **Soyouz**

Écoute le contrôle de mission faire le tour des postes, vis le compte à rebours, puis décolle dans un nuage de fumée. Traverse les nuages, passe le mur du son et le Max-Q, largue tes boosters (la célèbre « croix de Korolev » du Soyouz), franchis la ligne de Kármán et entre dans l'espace.

Amarre-toi à la Station spatiale internationale pour refaire le plein, file vers la Lune, puis pose ton module lunaire en douceur sur la Mer de la Tranquillité.

- Terre, Lune, atmosphère et nuages en 3D temps réel
- 4 vues : poursuite, cockpit, caméra embarquée, caméra au sol
- Contrôle de mission en français avec voix
- 12 succès à débloquer
- Fonctionne sur ordinateur et sur téléphone

**Commandes** : flèches ou ZQSD pour piloter, Espace pour le boost, C pour changer de vue. Sur téléphone : glisse le doigt et utilise le bouton BOOST.

## Description to copy (English)

**Fly a real rocket from the Earth to the Moon!**

Pick your launch site and rocket:
- **Kourou** (French Guiana) with **Ariane 6**
- **Cape Canaveral** (Florida) with **Falcon 9**
- **Baikonur** (Kazakhstan) with **Soyuz**

Listen to mission control run the go/no-go poll, live the countdown and lift off in a cloud of smoke. Punch through the clouds, break the sound barrier, survive Max-Q, drop your boosters (including the famous Soyuz "Korolev cross"), cross the Kármán line and reach space.

Dock with the International Space Station to refuel, fly to the Moon and gently land your lunar module in the Sea of Tranquility.

- Real-time 3D Earth, Moon, atmosphere and clouds
- 4 camera views: chase, cockpit, onboard camera, ground tracking camera
- Mission control callouts (game text and voice in French)
- 12 achievements to unlock
- Plays on desktop and mobile

**Controls**: arrow keys or WASD to steer, Space to boost, C to switch views. On mobile: drag your finger and use the BOOST button.
