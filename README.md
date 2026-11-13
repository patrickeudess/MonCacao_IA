# Mon Cacao — première version professionnelle

Une application Flask pour suivre les producteurs et les données réelles collectées sur le terrain.

## Périmètre

- Connexion professionnelle, session de huit heures et déconnexion.
- Création, recherche et modification des fiches producteurs.
- Saisie et correction des récoltes : date, surface, âge du verger, poids, prix, coûts et observations.
- Historique par producteur et conseils datés, attribués au professionnel qui les saisit.
- Tableau de bord : producteurs, nombre de récoltes, poids et revenus calculés.
- Exports CSV des producteurs, récoltes et conseils.

Les comptes producteurs, assistant IA, prédictions, score écologique, messagerie, notifications, badges, cartographie, rapports PDF et synchronisation hors ligne ont été retirés du parcours et du serveur V1. Les versions précédentes restent dans Git. Le modèle et le script d'entraînement sont conservés pour un travail ultérieur ; ils ne sont pas exécutés par la V1. Le script historique génère des données synthétiques : cela ne permet pas de conclure à la provenance du modèle livré ni à celle des données terrain du propriétaire.

## Lancement local (PowerShell, Python 3.12)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app v1:create_app create-professional
.\.venv\Scripts\python.exe api_server.py
```

Ouvrir http://localhost:5000. L'administrateur crée le compte avec les invites de la commande ; le mot de passe n'est pas affiché. Aucun compte ni mot de passe par défaut n'est livré. Si le port est occupé, définir `$env:PORT = "5050"` avant le lancement.

## Données et unités

La V1 utilise `instance/v1.sqlite`, distincte de `data.sqlite` et de l'ancienne base `mon_cacao.db`. Elle ne modifie ni n'importe automatiquement les anciennes données. Leur reprise est une étape séparée : confirmer le propriétaire de chaque fiche, la signification des dates, les unités et le caractère cumulé ou individuel des volumes avant import. Les identifiants des anciens comptes locaux ne sont pas assimilés aux nouveaux comptes.

Une ligne représente une récolte d'un producteur à une date. Si plusieurs collectes ont lieu le même jour, les regrouper et utiliser un prix moyen pondéré ; ne pas ressaisir un cumul déjà enregistré. Les coûts concernent cette récolte, pas l'ensemble de l'exploitation. Le revenu est `poids en kg × prix FCFA/kg`. Le tableau de bord cumule toutes les dates et ne présente pas de rendement annuel ni de bénéfice net.

Les conseils sont rédigés par le professionnel ; le logiciel ne certifie pas une validation agronomique. Il ne fournit pas de recommandation automatique de traitement.

## Administration

```powershell
.\.venv\Scripts\python.exe -m flask --app v1:create_app reset-password
.\.venv\Scripts\python.exe -m flask --app v1:create_app backup backups/sauvegarde-2026-11-13.sqlite
```

La réinitialisation révoque les sessions du compte. La sauvegarde refuse d'écraser un fichier existant et utilise l'API de sauvegarde SQLite. Pour restaurer : arrêter le serveur, conserver une copie de la base actuelle, copier une sauvegarde vérifiée à l'emplacement configuré, puis redémarrer et vérifier les comptes et effectifs.

## Vérifications

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
```

Les tests utilisent des bases temporaires séparées. Ils couvrent le parcours, les calculs, la persistance, l'isolation des comptes, CSRF, expiration et révocation de session, limitation des connexions, validation des données, doublons, CSV et sauvegarde. Une vérification manuelle dans le navigateur couvre connexion, création d'une fiche, récolte, conseil et affichage mobile à 390 px.

## Structure

- `v1.py` : API, validation, accès aux données et commandes d'administration.
- `api_server.py` : lancement Waitress sans débogueur.
- `templates/index.html`, `static/` : interface française sans dépendance CDN.
- `tests/` : tests d'intégration.
- `requirements-model.txt` : anciennes dépendances, conservées uniquement pour la recherche sur le modèle.

Voir DEPLOYMENT.md pour le passage à un pilote hébergé.
