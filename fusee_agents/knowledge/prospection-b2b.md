# Prospecter des entreprises (légalement)

## Le cadre en France (RGPD / CNIL)
- **E-mail à un professionnel** : autorisé sans consentement préalable **si le message concerne son métier**
  (proposer un site à un restaurant : oui), avec identification claire de l'expéditeur et un moyen simple de
  refuser les prochains messages. Utiliser des adresses professionnelles publiques (site de l'entreprise).
- **E-mail à un particulier** : interdit sans consentement préalable. Pas de prospection de particuliers par e-mail.
- **Téléphone aux particuliers** : vérifier Bloctel — Fusée ne fait pas de démarchage téléphonique.
- Garder une liste « ne plus contacter » et la respecter. Ne pas acheter de fichiers d'adresses.
- Pour Fusée, ces règles sont appliquées automatiquement : campagne validée par Patron (create_campaign), seulement
  des entreprises avec une adresse publique et sa source (add_prospect), identité + raison du contact + lien de
  désinscription ajoutés à chaque e-mail, 1 relance maximum, arrêt dès une réponse, STOP respecté pour toujours,
  plafond par jour, envois en semaine 9 h-18 h. Patron mineur : un parent signe devis et contrats.

## Le déroulé dans Fusée
create_campaign → (validation) → find_contact_email + add_prospect (notes réelles) → maquette gratuite si possible
→ send_prospect_email (personnalisé) → relance automatique à J+5 → réponses chez Iris → list_prospects pour suivre.
Repères : un bon taux de réponse en prospection froide est de 5 à 15 % ; en dessous de 3 %, change l'objet,
la cible ou l'offre avant d'envoyer plus.

## Le message qui marche
- Court (< 120 mots), personnalisé (un vrai détail sur l'entreprise), un seul bénéfice, une seule question.
- Objet court et précis (« Votre site, boulangerie Martin ? »), jamais trompeur (pas de faux « Re: »).
- Exemple : « Bonjour, j'ai vu que la boulangerie n'a pas encore de site : vos clients ne trouvent pas vos horaires
  sur Google. J'ai préparé une maquette gratuite de ce que ça pourrait donner [lien]. Ça vous intéresse d'en
  parler 10 minutes ? »
- **La maquette gratuite déjà faite** (create_site_from_template « vitrine ») est l'argument le plus fort.
- Relance unique 4-7 jours plus tard. Pas de réponse → on n'insiste pas.

## Du « oui » à la vente
Devis clair (prestations, délais, prix HT, acompte 30-50 %), validation par Patron/un parent, facture.
