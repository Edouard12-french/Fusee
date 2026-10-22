# Fusee

## Jeu : Fusée Kármán

Jeu 3D dans le navigateur (Three.js + WebGL) : la fusée décolle, traverse les nuages, passe le mur du son et monte jusqu'à la ligne de Kármán (100 km), puis jusqu'à l'orbite de l'ISS. La Terre, l'atmosphère et les nuages sont calculés en temps réel. Il faut esquiver les avions, ballons-sondes, météorites, satellites et débris, et ramasser les réservoirs de carburant.

Commandes : flèches ou ZQSD/WASD pour piloter, Espace pour le boost, M pour couper le son. Sur mobile : glisser le doigt, bouton BOOST.

Pour y jouer en local, ouvre `jeu/index.html` dans un navigateur.

### Publier sur itch.io

1. Compresse le dossier `jeu` en `.zip` : `index.html` et `three.min.js` doivent être à la racine du zip.
2. Sur itch.io : « Upload new project », « Kind of project » = **HTML**.
3. Envoie le zip et coche « This file will be played in the browser ».
4. Taille conseillée : 960 × 640, avec le bouton plein écran activé.
5. Prix : « No payment required » avec dons, ou « Pay what you want ».
