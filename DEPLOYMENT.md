# Mise en service du pilote

Cette livraison est une version locale testée, pas un déploiement public.

## Serveur

Installer Python 3.12 et les dépendances de requirements.txt dans un environnement isolé. Lancer `python api_server.py` avec un superviseur de processus et un reverse proxy HTTPS. Ne pas servir le dossier du dépôt avec un serveur de fichiers : il contient des données historiques et le modèle. Seuls Flask et son dossier static doivent être exposés.

Variables :
- `MONCACAO_DATABASE` : chemin absolu d'une base SQLite sur un disque persistant, hors du dossier public.
- `MONCACAO_HTTPS=1` : cookie Secure obligatoire derrière HTTPS.
- `PORT` : port interne, 5000 par défaut.
- `MONCACAO_HOST` : 127.0.0.1 par défaut ; ne changer que selon la configuration réseau de l'hébergement.

Créer les comptes par `python -m flask --app v1:create_app create-professional`. Les mots de passe sont hachés avec Werkzeug ; les jetons de session sont aléatoires, stockés hachés côté serveur et envoyés dans un cookie HttpOnly/SameSite. Les écritures exigent un jeton CSRF. Chaque requête vérifie le propriétaire des producteurs. Dix essais de connexion par identifiant sont autorisés sur quinze minutes ; prévoir également une limitation par adresse côté reverse proxy pour un pilote exposé.

La base SQLite convient à un petit pilote sur une instance avec disque local persistant. Ne pas utiliser un système de fichiers réseau ou éphémère ni multiplier les instances avec des copies séparées de la base. Les pages et réponses ne sont pas mises en cache. Une connexion réseau est nécessaire pour enregistrer.

## Données existantes

Les données et le modèle historiques sont conservés. Aucun volume, prix, compte ou identité n'est migré automatiquement. Préparer un import explicite et vérifiable avant d'utiliser la V1 comme remplacement du système existant : mapping des propriétaires, unités, dates, doublons, effectifs avant/après, et sauvegarde préalable. Les anciennes soumissions ne sont pas nécessairement des récoltes distinctes.

## Avant ouverture aux utilisateurs

1. Configurer HTTPS, cookie Secure, disque persistant et sauvegardes hors du serveur.
2. Créer les vrais comptes, sans réutiliser le compte de vérification local.
3. Vérifier la restauration d'une sauvegarde et les droits d'accès sur l'hébergement choisi.
4. Faire valider les champs et les conseils par les professionnels du pilote.
5. Confirmer les règles de collecte, de conservation et d'accès avec l'organisation responsable.

## Revenir à la version précédente

Le point de départ du travail est le commit f0994e6306f7121ac4e181d07351a25097e8bcaf du dépôt MonCacao_IA. L'ancienne application reste récupérable dans Git. Les bases de l'ancienne application et de la V1 sont séparées ; revenir au code précédent ne convertit pas les données V1.
