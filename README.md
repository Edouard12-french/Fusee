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

## Jeu : Escadron Phénix

Combat aérien en 3D dans le navigateur (Three.js + WebGL), au-dessus d'un archipel tropical :

- 6 missions de campagne : entraînement (anneaux et drones), interception, destruction de radars, protection d'un convoi contre des bombardiers, attaque d'une flotte avec porte-avions, duel contre le Baron Rouge.
- Combat libre : des vagues d'ennemis sans fin, avec réparation entre chaque vague.
- Canon avec aide à la visée, missiles à verrouillage, leurres contre les missiles ennemis, postcombustion.
- Ennemis pilotés par l'ordinateur (poursuite, esquive, leurres), ailier allié, défense antiaérienne sur les navires et les îles.
- 3 avions (Faucon, Orage, Titan) et 5 peintures à débloquer avec les étoiles, 12 succès, 3 difficultés.
- Vues : poursuite, cockpit, cinéma. Radio en français avec voix.
- Clavier, manette ou écran tactile.

Pour y jouer en local, ouvre `escadron/index.html`.

## Jeu : Ours Malin

Aventure 3D tout en douceur dans le parc des Pins. Le but : sauver le parc que M. Béton veut raser, en gagnant 7 étoiles du parc. Oscar l'ours chipe des pique-niques, se déguise, pêche, ramasse les déchets, sauve des bébés animaux, répare le village des cabanes dans les arbres, puis fait voler un camping-car pour montrer le parc à la maire.

- 14 missions qui se suivent, avec Max le castor, Lulu la loutre, Raflex le raton laveur (son musée), Donovan le canard (course contre la montre), Noisette l'écureuil, Madame Plume la chouette et Papi Blaireau.
- Une ligne blanche au sol guide vers l'objectif.
- Animaux de la forêt (cerfs, lapins, renards, canards, oiseaux, papillons, poissons qui sautent) et personnages qui parlent avec leur voix.
- Une rivière, un ruisseau avec des ponts, 5 lacs (dont le lac d'Oscar), une montagne et beaucoup d'arbres.
- 9 cabanes dans les arbres reliées par des ponts de corde (le village des arbres et les cabanes du lac).
- La maison d'Oscar dans sa grotte : lit de feuilles pour dormir, cheminée et étagère à trophées. Deux grottes à explorer (cristaux et fossile).
- Discrétion : cônes de vision des campeurs et du garde Gérard, buissons pour se cacher, poursuites.
- Cycle jour et nuit, pêche (8 poissons), fouilles au trésor, boutiques du village, chapeaux à acheter.
- Camping-car à conduire, puis à faire voler à travers 8 anneaux.
- 12 pommes de pin dorées à trouver, sauvegarde automatique, clavier ou écran tactile.

Pour y jouer en local, ouvre `ours/index.html`. Pour itch.io, tout est dans `itch/ours/` (zip, couverture, captures et guide `PAGE-ITCH.md`).
