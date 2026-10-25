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

Aventure 3D tout en douceur dans le parc des Pins, avec Oscar, un ours un peu bête, très drôle et têtu. Le but : sauver le parc que M. Béton veut raser, en gagnant 7 étoiles du parc. Oscar l'ours chipe des pique-niques, se déguise, pêche, ramasse les déchets, sauve des bébés animaux, répare le village des cabanes dans les arbres, puis construit un camping-car avec Max (6 pièces à trouver chez les amis et dans le parc : châssis, roues, carrosserie, volant et sièges, moteur, phares) et le fait voler pour montrer le parc à la maire.

- 14 missions qui se suivent, avec Max le castor, Lulu la loutre, Raflex le raton laveur (son musée), Donovan le canard (course contre la montre), Noisette l'écureuil, Madame Plume la chouette et Papi Blaireau.
- Une ligne blanche au sol guide vers l'objectif pendant les deux premières missions.
- Animaux de la forêt (cerfs, lapins, renards, canards, oiseaux, papillons, poissons qui sautent) et personnages qui parlent dans des bulles.
- Une rivière, un ruisseau avec des ponts, 5 lacs (dont le lac d'Oscar), une montagne et beaucoup d'arbres.
- 9 cabanes dans les arbres reliées par des ponts de corde (le village des arbres et les cabanes du lac).
- La maison d'Oscar dans sa grotte : lit de feuilles pour dormir, cheminée et étagère à trophées. Deux grottes à explorer (cristaux et fossile).
- Une carte deux fois et demie plus grande, avec de nouvelles zones autour du parc :
  - au nord, la station de ski du Pic Grizzly : montagnes enneigées, 3 pistes, 2 télésièges sur lesquels on s'assoit, le chalet d'Yvette (luge, skis, bonnet), Marcel au télésiège et Cabriole la chèvre et son slalom ;
  - à l'ouest, la grande forêt avec des séquoias géants, des fougères, des champignons à cueillir et Elliot l'élan ;
  - à l'est, la grande prairie avec les bisons, le moulin à vent et la ferme des tournesols, et au sud-est le canyon rouge ;
  - au sud, le marais avec ses passerelles en bois, ses roseaux et ses nénuphars.
- 10 animaux sauvages à noter dans le carnet d'Elliot : élan, loup, sanglier, bison, bouquetin, marmotte, aigle royal, héron, grenouille et lynx.
- Des nuages qui passent dans le ciel (leur ombre glisse sur le sol), de la neige qui tombe en montagne et une mer de nuages au bord du monde.
- Des défis en plus des 14 missions : monter au sommet, le slalom, le carnet sauvage. Ils sont listés dans le journal.
- 6 aventures du Grand Nord en plus de l'histoire : le louveteau perdu (Elliot), le chocolat chaud d'Yvette, les cristaux de glace et la luge dorée (Cabriole), le marais tout propre (Gaspard le héron), les poules de Josette et le petit bison de Bernard. Chaque aventure est notée sur la carte.
- La météo change : averses de pluie (ou de neige en montagne) avec arc-en-ciel après, lucioles la nuit et loups qui hurlent.
- Une patinoire sur le lac gelé du Glacier, où Oscar glisse sur la glace.
- De nouveaux amis, de vrais animaux : Maurice et Praline les carlins (cache-cache), Roquette le raton laveur (course de luge) et Filou le renard (devinettes).
- Oscar et tous ses amis ressemblent à de vrais animaux, avec des détails (moustaches, touffes de poils, plumes, coussinets) : Max le castor, Lulu la loutre, Raflex le raton laveur, Donovan le colvert, Noisette l'écureuil roux, Papi Blaireau et Madame Plume le hibou grand-duc.
- Le rêve d'Oscar : aller dans l'espace avec son camping-car volant. Il choisit un métier au panneau « Offres d'emploi » du village pour payer la transformation :
  - facteur : distribuer les lettres dans les boîtes aux lettres des maisons des amis (chacun a sa maison avec son nom) ;
  - pilote d'avion : décoller de l'aéroport de la grande prairie et passer dans les anneaux au-dessus du parc ;
  - capitaine de bateau : emmener des passagers d'un ponton à l'autre sur le grand lac.
  Les pièces vont dans la tirelire de Max, à côté de son atelier (4000 pièces). Max transforme le camping-car volant en camping-car spatial en 4 étapes (réacteurs, coque spatiale, bulle d'oxygène, antenne), et tous les amis viennent aider à chaque étape.
- Chapitre 2, le grand jour : tous les amis montent à bord à la base de lancement du canyon rouge. Le camping-car monte doucement au-dessus du parc pour admirer le paysage, le ciel devient noir, puis on se pose sur la Lune (on peut passer la scène).
- Sur la Lune, une petite planète ronde avec des cratères et une montagne, nos héros découvrent par hasard les Zoublis, des petits extraterrestres dont la soucoupe est en panne. 5 missions pour les aider à rentrer chez eux : les rencontrer, trouver 5 cristaux d'énergie, rapporter 3 blocs de glace pour le carburant, régler 3 télescopes pour retrouver leur planète, puis leur dire au revoir. Ensuite, on peut aller et venir entre la Terre et la Lune.
- Chapitre 3, la Forêt Immense : en rentrant de la Lune, une pluie d'étoiles filantes touche le camping-car. Il s'écrase dans une forêt géante et brumeuse, et les amis sautent avec des feuilles-parachutes. Oscar se réveille seul et rencontre Brume, un grand cerf blanc. 6 missions :
  1. parler à Brume ;
  2. retrouver les 11 amis perdus (au bord de la rivière, au lac des Brumes, dans les ruines anciennes, au milieu des champignons géants, dans un tronc creux…) ;
  3. trouver les 3 pièces tombées du camping-car (réacteur, antenne, bulle d'oxygène) ;
  4. rallumer les 3 pierres-lanternes pour chasser la brume magique ;
  5. réveiller l'Arbre-Mère, qui se couvre de fleurs lumineuses et donne une graine ;
  6. rentrer au parc et planter la graine près de la grotte d'Oscar.
  À la fin, Madame Plume voit la mer du haut de l'Arbre-Mère, avec des lumières sous l'eau : un peuple des mers, pour une prochaine aventure ?
- La Forêt Immense : arbres géants et séquoias de plus de 30 mètres, lianes, racines, rivière avec des ponts en troncs, lac des Brumes, ruines anciennes, champignons géants et petits champignons qui brillent la nuit, arbres à lanternes, rayons de soleil entre les arbres, brume qui flotte, lucioles, cerfs et lapins. La caméra passe sous les grands arbres.
- Oscar a du caractère : c'est un ours un peu bête, très drôle et têtu. Il est gourmand, il se croit le plus malin et il ne veut jamais avoir tort. Il pense tout haut dans une petite bulle : quand il reste sans bouger, quand il fonce dans un arbre (il insiste !), quand il nage, court, mange des baies, se promène la nuit, dans la forêt ou sur la Lune.
- Graphismes plus beaux : les herbes, fleurs et feuillages bougent avec le vent, un vrai ciel avec un soleil qui brille et des étoiles la nuit, de l'eau qui brille, des feuilles qui tombent dans la forêt, des graines qui volent dans la prairie et un léger voile sombre au bord de l'écran.
- Des avions dans le ciel, des voiliers sur le lac, une musique plus riche avec une mélodie à la flûte, plus d'arbres, des souches, des troncs couchés et des rochers moussus.
- Les personnages ne parlent plus à voix haute (on lit les bulles), et la flèche orange n'apparaît que pour les deux premières missions : ensuite, on utilise la carte.
- Discrétion : cônes de vision des campeurs et du garde Gérard, buissons pour se cacher, poursuites.
- Cycle jour et nuit, pêche (8 poissons), fouilles au trésor, boutiques du village, chapeaux à acheter.
- Camping-car à conduire, puis à faire voler à travers 8 anneaux.
- 12 pommes de pin dorées à trouver, sauvegarde automatique, clavier ou écran tactile.

Pour y jouer en local, ouvre `ours/index.html`. Pour itch.io, tout est dans `itch/ours/` (zip, couverture, captures et guide `PAGE-ITCH.md`).
