# Fusee

## Jeu : Fusée Kármán

Jeu 3D dans le navigateur (Three.js + WebGL), une mission complète de la Terre à la Lune :

1. **Décollage** avec le vrai lanceur de chaque base : Ariane 6 à Kourou (pas de tir ELA-4, portique mobile), Falcon 9 à Cap Canaveral (pas de tir 39A, tour de service et bras érecteur), Soyouz à Baïkonour (pas de tir 31, bras « tulipe » au-dessus de la fosse). Les étages se séparent en vol : boosters, premier étage, coiffe, puis l'étage supérieur. C'est le module lunaire qui se pose.
2. **Ascension** : nuages, mur du son, Max-Q, ligne de Kármán (100 km). Il faut esquiver avions, ballons-sondes, météorites, satellites et débris, et ramasser les réservoirs.
3. **Station spatiale** : passer dans l'anneau vert pour s'amarrer à l'ISS et refaire le plein.
4. **Voyage vers la Lune** : injection trans-lunaire, astéroïdes, la Lune qui grossit.
5. **Orbite lunaire** et station Gateway, avec la Terre au-dessus de l'horizon.
6. **Alunissage manuel** : freiner et viser la cible pour se poser à moins de 3 m/s.

La Terre, la Lune, l'atmosphère et les nuages sont calculés en temps réel dans un shader.

Contrôle de mission : le directeur de lancement fait le tour des postes (Propulsion, Guidage, Météo, Sauvegarde vol), puis chaque poste annonce les étapes du vol dans un panneau radio, avec une voix en français si le navigateur le permet.

Vues (touche C) : poursuite, cockpit avec tableau de bord, caméra embarquée sur le flanc, caméra extérieure (suivi au sol avec zoom, puis vue de côté).

Commandes : flèches ou ZQSD/WASD pour piloter, Espace pour le boost (et la poussée pendant l'alunissage), C pour changer de vue, V pour la voix, M pour couper le son, P ou Échap pour la pause. Sur mobile : glisser le doigt, bouton BOOST.

Pour y jouer en local, ouvre `jeu/index.html` dans un navigateur.

### Publier sur itch.io

Tout est prêt dans le dossier `itch/` : le zip du jeu, l'image de couverture, les captures d'écran et le guide pas à pas avec les textes de la page (`itch/PAGE-ITCH.md`). Le résumé :

1. Compresse le dossier `jeu` en `.zip` : `index.html` et `three.min.js` doivent être à la racine du zip.
2. Sur itch.io : « Upload new project », « Kind of project » = **HTML**.
3. Envoie le zip et coche « This file will be played in the browser ».
4. Taille conseillée : 960 × 640, avec le bouton plein écran activé.
5. Prix : « No payment required » avec dons, ou « Pay what you want ».
