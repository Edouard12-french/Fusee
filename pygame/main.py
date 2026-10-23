# Fusée Kármán 2D, la version Python qu'on code ensemble.
# Lancer sur l'ordi :  python main.py
# Commandes : flèches (ou ZQSD) pour bouger, Espace pour recommencer.
# Sur téléphone : glisse le doigt pour bouger la fusée.

import asyncio  # Obligatoire pour que le jeu marche dans le navigateur (itch.io)
import math
import random

import pygame

# ---------- 1. Les réglages du jeu ----------
LARGEUR, HAUTEUR = 480, 720
IMAGES_PAR_SECONDE = 60
ALTITUDE_KARMAN = 100        # km : là où commence l'espace
ALTITUDE_LUNE = 384400       # km : la distance de la Lune

nom = "Kármán"               # Tu peux changer le nom de ta fusée ici !

pygame.init()
ecran = pygame.display.set_mode((LARGEUR, HAUTEUR))
pygame.display.set_caption("Fusée " + nom)
horloge = pygame.time.Clock()
police = pygame.font.Font(None, 30)
grande_police = pygame.font.Font(None, 64)


# ---------- 2. Les petites fonctions utiles ----------
def melanger(couleur1, couleur2, t):
    """Mélange deux couleurs. t = 0 donne couleur1, t = 1 donne couleur2."""
    t = max(0, min(1, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(couleur1, couleur2))


def ecrire(texte, x, y, taille=police, couleur=(255, 255, 255), centre=False):
    image = taille.render(texte, True, couleur)
    ombre = taille.render(texte, True, (0, 0, 0))  # L'ombre rend le texte lisible sur les nuages
    if centre:
        x -= image.get_width() // 2
    ecran.blit(ombre, (x + 2, y + 2))
    ecran.blit(image, (x, y))


def zone_de_vol(altitude):
    if altitude < 12:
        return "Troposphère"
    if altitude < 50:
        return "Stratosphère"
    if altitude < ALTITUDE_KARMAN:
        return "Mésosphère"
    if altitude < 36000:
        return "Orbite terrestre"
    return "Vers la Lune"


# ---------- 3. La fusée ----------
class Fusee:
    def __init__(self):
        self.x = LARGEUR / 2
        self.y = HAUTEUR - 160
        self.carburant = 100
        self.vies = 3
        self.invincible = 0  # Temps (en secondes) pendant lequel on ne peut pas être touché

    def bouger(self, touches, doigt, dt):
        vitesse = 300
        if touches[pygame.K_LEFT] or touches[pygame.K_q] or touches[pygame.K_a]:
            self.x -= vitesse * dt
        if touches[pygame.K_RIGHT] or touches[pygame.K_d]:
            self.x += vitesse * dt
        if touches[pygame.K_UP] or touches[pygame.K_z] or touches[pygame.K_w]:
            self.y -= vitesse * dt
        if touches[pygame.K_DOWN] or touches[pygame.K_s]:
            self.y += vitesse * dt
        if doigt:  # La fusée suit le doigt (ou la souris)
            self.x += (doigt[0] - self.x) * min(1, 8 * dt)
            self.y += (doigt[1] - 60 - self.y) * min(1, 8 * dt)
        # La fusée ne doit pas sortir de l'écran
        self.x = max(25, min(LARGEUR - 25, self.x))
        self.y = max(80, min(HAUTEUR - 70, self.y))

    def rectangle(self):
        """La zone qui compte pour les collisions (un peu plus petite que le dessin)."""
        return pygame.Rect(self.x - 11, self.y - 30, 22, 70)

    def dessiner(self, temps):
        # Clignote quand elle vient d'être touchée
        if self.invincible > 0 and int(temps * 10) % 2 == 0:
            return
        x, y = self.x, self.y
        # Flamme qui tremble
        longueur = 30 + random.randint(0, 14)
        pygame.draw.polygon(ecran, (255, 140, 30), [(x - 10, y + 40), (x + 10, y + 40), (x, y + 40 + longueur)])
        pygame.draw.polygon(ecran, (255, 240, 160), [(x - 5, y + 40), (x + 5, y + 40), (x, y + 40 + longueur * 0.6)])
        # Ailerons
        pygame.draw.polygon(ecran, (200, 40, 40), [(x - 14, y + 15), (x - 26, y + 42), (x - 14, y + 38)])
        pygame.draw.polygon(ecran, (200, 40, 40), [(x + 14, y + 15), (x + 26, y + 42), (x + 14, y + 38)])
        # Corps et nez
        pygame.draw.rect(ecran, (240, 240, 245), (x - 14, y - 20, 28, 60), border_radius=6)
        pygame.draw.polygon(ecran, (240, 240, 245), [(x - 14, y - 18), (x + 14, y - 18), (x, y - 50)])
        pygame.draw.rect(ecran, (60, 60, 70), (x - 14, y + 34, 28, 6))
        # Hublot
        pygame.draw.circle(ecran, (40, 120, 200), (int(x), int(y - 2)), 7)
        pygame.draw.circle(ecran, (255, 255, 255), (int(x), int(y - 2)), 7, 2)


# ---------- 4. Les obstacles et les bonus ----------
class Objet:
    def __init__(self, sorte):
        self.sorte = sorte  # "avion", "ballon", "satellite", "asteroide" ou "carburant"
        self.x = random.randint(30, LARGEUR - 30)
        self.y = -40
        self.vx = random.uniform(-40, 40)
        self.taille = random.randint(18, 30) if sorte == "asteroide" else 22
        self.angle = random.uniform(0, 6.28)

    def avancer(self, vitesse_defilement, dt):
        self.y += vitesse_defilement * dt
        self.x += self.vx * dt
        self.angle += dt

    def rectangle(self):
        t = self.taille
        return pygame.Rect(self.x - t * 0.8, self.y - t * 0.8, t * 1.6, t * 1.6)

    def dessiner(self):
        x, y, t = int(self.x), int(self.y), self.taille
        if self.sorte == "carburant":
            pygame.draw.rect(ecran, (255, 190, 40), (x - 12, y - 16, 24, 32), border_radius=4)
            ecrire("F", x, y - 10, couleur=(60, 30, 0), centre=True)
        elif self.sorte == "avion":
            pygame.draw.ellipse(ecran, (230, 230, 230), (x - 30, y - 6, 60, 12))
            pygame.draw.polygon(ecran, (200, 200, 210), [(x - 4, y), (x + 8, y), (x - 10, y + 22), (x - 18, y + 22)])
            pygame.draw.polygon(ecran, (200, 200, 210), [(x - 4, y), (x + 8, y), (x - 10, y - 22), (x - 18, y - 22)])
        elif self.sorte == "ballon":
            pygame.draw.line(ecran, (200, 200, 200), (x, y + 18), (x, y + 34), 1)
            pygame.draw.circle(ecran, (245, 245, 250), (x, y), 18)
        elif self.sorte == "satellite":
            pygame.draw.rect(ecran, (200, 170, 60), (x - 8, y - 8, 16, 16))
            pygame.draw.rect(ecran, (40, 70, 160), (x - 34, y - 6, 22, 12))
            pygame.draw.rect(ecran, (40, 70, 160), (x + 12, y - 6, 22, 12))
        else:  # astéroïde : un rocher avec des bosses
            points = []
            for i in range(9):
                a = self.angle + i * 6.28 / 9
                r = t * (0.8 + 0.25 * math.sin(i * 2.7))
                points.append((x + math.cos(a) * r, y + math.sin(a) * r))
            pygame.draw.polygon(ecran, (120, 105, 95), points)
            pygame.draw.circle(ecran, (90, 80, 72), (x - t // 4, y - t // 5), t // 4)


def choisir_obstacle(altitude):
    """Dans le ciel il y a des ballons, puis des satellites et des astéroïdes."""
    if altitude < ALTITUDE_KARMAN:
        return "ballon"
    if altitude < 36000:
        return random.choice(["satellite", "satellite", "asteroide"])
    return "asteroide"


# ---------- 5. Le décor ----------
etoiles = [(random.randint(0, LARGEUR), random.randint(0, HAUTEUR), random.random()) for _ in range(140)]
nuages = [[random.randint(0, LARGEUR), random.randint(0, HAUTEUR), random.randint(40, 90)] for _ in range(6)]


def dessiner_decor(altitude, vitesse_defilement, dt):
    # Le ciel devient noir en montant (bleu en bas, noir dans l'espace)
    t = min(1, altitude / ALTITUDE_KARMAN)
    ecran.fill(melanger((90, 160, 230), (3, 4, 12), t))

    # Les étoiles apparaissent petit à petit
    if t > 0.3:
        for i, (x, y, lumiere) in enumerate(etoiles):
            y = (y + vitesse_defilement * dt * 0.1 * (0.5 + lumiere)) % HAUTEUR
            etoiles[i] = (x, y, lumiere)
            gris = int(255 * lumiere * (t - 0.3) / 0.7)
            ecran.set_at((x, int(y)), (gris, gris, gris))

    # Les nuages, seulement en bas de l'atmosphère
    if altitude < 15:
        for n in nuages:
            n[1] += vitesse_defilement * dt * 0.7
            if n[1] > HAUTEUR + 60:
                n[0], n[1] = random.randint(0, LARGEUR), -60
            for dx in (-n[2] // 2, 0, n[2] // 2):
                pygame.draw.circle(ecran, (245, 248, 252), (n[0] + dx, int(n[1])), n[2] // 2)

    # La Terre, qui s'éloigne en bas de l'écran
    if altitude < 2000:
        rayon = 2400
        centre_y = HAUTEUR + rayon - 120 + int(altitude * 8)
        pygame.draw.circle(ecran, (40, 110, 70), (LARGEUR // 2, centre_y), rayon)

    # La Lune grossit quand on s'approche
    if altitude > 36000:
        progression = (altitude - 36000) / (ALTITUDE_LUNE - 36000)
        rayon = int(10 + 250 * progression ** 2)
        pygame.draw.circle(ecran, (200, 200, 195), (LARGEUR // 2, 40 + rayon // 3), rayon)
        pygame.draw.circle(ecran, (170, 170, 165), (LARGEUR // 2 - rayon // 3, 40 + rayon // 4), rayon // 5)


def dessiner_infos(fusee, altitude, score):
    ecrire(f"Altitude : {int(altitude):,} km".replace(",", " "), 12, 10)
    ecrire(zone_de_vol(altitude), 12, 36, couleur=(160, 200, 255))
    ecrire(f"Score : {score}", 12, 62)
    ecrire("Vies :", LARGEUR - 150, 36, couleur=(255, 120, 120))
    for i in range(fusee.vies):  # Un petit cœur rouge par vie
        x = LARGEUR - 82 + i * 22
        pygame.draw.circle(ecran, (255, 80, 90), (x - 4, 44), 5)
        pygame.draw.circle(ecran, (255, 80, 90), (x + 4, 44), 5)
        pygame.draw.polygon(ecran, (255, 80, 90), [(x - 9, 46), (x + 9, 46), (x, 56)])
    # La jauge de carburant (rouge quand il en reste peu)
    couleur = (255, 190, 40) if fusee.carburant > 25 else (255, 60, 60)
    pygame.draw.rect(ecran, (40, 40, 50), (LARGEUR - 150, 14, 136, 14))
    pygame.draw.rect(ecran, couleur, (LARGEUR - 150, 14, int(1.36 * fusee.carburant), 14))


# ---------- 6. La boucle du jeu ----------
async def main():
    etat = "menu"  # "menu", "vol", "perdu" ou "gagne"
    fusee = Fusee()
    objets = []
    altitude = 0
    score = 0
    temps = 0
    prochain_obstacle = 1
    prochain_carburant = 2
    message = ""
    doigt = None

    while True:
        dt = horloge.tick(IMAGES_PAR_SECONDE) / 1000  # Temps écoulé depuis l'image d'avant
        temps += dt

        # --- Les touches et le doigt ---
        commencer = False
        for evenement in pygame.event.get():
            if evenement.type == pygame.QUIT:
                pygame.quit()
                return
            if evenement.type == pygame.KEYDOWN and evenement.key in (pygame.K_SPACE, pygame.K_RETURN):
                commencer = True
            if evenement.type == pygame.MOUSEBUTTONDOWN:
                commencer = True
                doigt = evenement.pos
            if evenement.type == pygame.MOUSEMOTION and evenement.buttons[0]:
                doigt = evenement.pos
            if evenement.type == pygame.MOUSEBUTTONUP:
                doigt = None

        if etat != "vol" and commencer:
            etat = "vol"
            fusee = Fusee()
            objets = []
            altitude = 0
            score = 0
            doigt = None

        # Plus on monte, plus on va vite (jusqu'à la Lune en 4 minutes environ)
        vitesse_km = min(2 + altitude / 20, 9000)
        vitesse_defilement = 220 + min(altitude, 400)  # Vitesse des objets à l'écran

        if etat == "vol":
            fusee.bouger(pygame.key.get_pressed(), doigt, dt)
            altitude += vitesse_km * dt
            fusee.carburant -= 2.2 * dt
            fusee.invincible = max(0, fusee.invincible - dt)
            score += int(vitesse_km * dt) + 1

            # On fait apparaître des obstacles, de plus en plus souvent
            prochain_obstacle -= dt
            if prochain_obstacle <= 0:
                objets.append(Objet(choisir_obstacle(altitude)))
                prochain_obstacle = max(0.45, 1.3 - altitude / 50000)
            prochain_carburant -= dt
            if prochain_carburant <= 0:
                objets.append(Objet("carburant"))
                prochain_carburant = random.uniform(3, 5)

            for objet in objets:
                objet.avancer(vitesse_defilement, dt)
            objets = [o for o in objets if o.y < HAUTEUR + 60]

            # Les collisions
            for objet in objets[:]:
                if not fusee.rectangle().colliderect(objet.rectangle()):
                    continue
                if objet.sorte == "carburant":
                    fusee.carburant = min(100, fusee.carburant + 30)
                    score += 100
                    objets.remove(objet)
                elif fusee.invincible == 0:
                    fusee.vies -= 1
                    fusee.invincible = 2
                    objets.remove(objet)

            # Gagné ou perdu ?
            if fusee.vies <= 0:
                etat, message = "perdu", "Fusée détruite !"
            elif fusee.carburant <= 0:
                etat, message = "perdu", "Plus de carburant !"
            elif altitude >= ALTITUDE_LUNE:
                etat, message = "gagne", "Sur la Lune !"

        # --- Le dessin ---
        dessiner_decor(altitude, vitesse_defilement if etat == "vol" else 30, dt)
        for objet in objets:
            objet.dessiner()
        fusee.dessiner(temps)

        if etat != "vol":
            # Un cadre sombre et transparent derrière les textes
            cadre = pygame.Surface((LARGEUR - 40, 240), pygame.SRCALPHA)
            cadre.fill((0, 10, 30, 150))
            ecran.blit(cadre, (20, 180))
        if etat == "menu":
            ecrire("FUSÉE " + nom.upper(), LARGEUR // 2, 200, grande_police, centre=True)
            ecrire("De la Terre jusqu'à la Lune", LARGEUR // 2, 260, centre=True)
            ecrire("Évite les obstacles, attrape le carburant", LARGEUR // 2, 300, couleur=(255, 190, 40), centre=True)
            ecrire("Espace ou touche l'écran pour décoller", LARGEUR // 2, 380, centre=True)
        else:
            dessiner_infos(fusee, altitude, score)
            if altitude > ALTITUDE_KARMAN and altitude < ALTITUDE_KARMAN + 30:
                ecrire("Ligne de Kármán : bienvenue dans l'espace !", LARGEUR // 2, 120, couleur=(255, 220, 120), centre=True)
        if etat in ("perdu", "gagne"):
            couleur = (120, 255, 160) if etat == "gagne" else (255, 110, 110)
            ecrire(message, LARGEUR // 2, 260, grande_police, couleur, centre=True)
            ecrire(f"Score : {score}", LARGEUR // 2, 330, centre=True)
            ecrire("Espace ou touche l'écran pour rejouer", LARGEUR // 2, 380, centre=True)

        pygame.display.flip()
        await asyncio.sleep(0)  # Laisse le navigateur respirer : à garder dans la boucle !


asyncio.run(main())
