# SKALAK AI — abonnements et paiements (version à configurer)

## Tarifs retenus
- SKALAK PRO : 1 500 FCFA / 30 jours
- SKALAK VIP : 4 500 FCFA / 30 jours
- Renouvellement manuel : l’utilisateur paie à nouveau chaque mois.

## Ce que contient ce projet
- Interface mobile en français
- Création de compte et connexion par e-mail/mot de passe
- Paiement Wave Checkout via API, lorsque la clé marchande est configurée
- Vérification du statut Wave côté serveur avant activation
- Demande de paiement Moov en attente avec confirmation marchande sécurisée
- Expiration après 30 jours
- Endpoints de matchs, prédictions, cotes et statistiques via API-Football

## Important — pas encore publié / paiement Moov à valider
Le projet ne sera pas automatiquement en ligne après téléchargement. Il faut un dépôt GitHub et un hébergement.
Wave : nécessite une clé API créée dans le portail Wave Business. Garde-la secrète.
Moov : la version incluse ne confirme PAS automatiquement un paiement Moov. Il faut que Moov/son partenaire fournisse une API marchande et sa documentation; jusqu'alors, un administrateur doit vérifier le paiement et le confirmer via le endpoint admin.
Les paiements ne doivent jamais être validés sur la seule base d'une capture d'écran ou d'une déclaration du client.
L'activation de l'abonnement est faite côté serveur uniquement après confirmation Wave ou confirmation administrateur Moov.

## Configuration Render
Le fichier render.yaml prépare les variables :
- `FLASK_SECRET_KEY` (générée par Render)
- `WAVE_API_KEY` (à obtenir auprès de Wave Business)
- `API_FOOTBALL_KEY` (à obtenir auprès d'API-Football)
- `ADMIN_TOKEN` (généré par Render)
- `MOOV_PAYMENT_INSTRUCTIONS` (à remplacer par les instructions marchand vérifiées)

Ne colle jamais les clés dans `index.html` ou dans un dépôt public. Ne partage pas `ADMIN_TOKEN`.

## Test local
Python 3.10+ :
1. `pip install -r requirements.txt`
2. Définis les variables d'environnement nécessaires.
3. `python app.py`
4. Ouvre `http://127.0.0.1:10000`

## Limites de production à traiter avant de vendre
- Ajouter confirmation e-mail / réinitialisation du mot de passe
- Utiliser une base PostgreSQL persistante en hébergement de production; SQLite peut perdre des données sur certains déploiements.
- Ajouter des limites anti-abus, protection CSRF, politique de confidentialité et conditions d'utilisation.
- Vérifier auprès de Wave et Moov les frais, autorisations et conditions marchandes.
- Ne pas promettre des gains aux paris; les analyses ne sont pas garanties.
