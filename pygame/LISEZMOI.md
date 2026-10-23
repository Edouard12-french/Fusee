# Fusée Kármán 2D (version Python / pygame)

## Jouer sur ton ordi

1. Installe Python depuis python.org.
2. Dans un terminal : `pip install pygame-ce`
3. Dans ce dossier : `python main.py`

## Mettre le jeu sur itch.io

1. Dans un terminal : `pip install pygbag`
2. Va dans le dossier qui contient le dossier `pygame`, puis tape : `pygbag --archive pygame`
3. Le zip est créé ici : `pygame/build/web.zip`.
4. Sur itch.io : « Kind of project » = **HTML**, envoie `web.zip` et coche « This file will be played in the browser ».
5. Taille de l'écran : **480 × 720**.

## Idées pour continuer ensemble

- Changer le nom de la fusée (la ligne `nom = "Kármán"`).
- Ajouter un bouton de boost qui fait monter plus vite mais consomme plus de carburant.
- Ajouter la station spatiale vers 400 km pour refaire le plein.
- Ajouter du son avec `pygame.mixer`.
