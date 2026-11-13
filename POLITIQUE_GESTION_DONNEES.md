# Données du pilote — fonctionnement technique

La V1 stocke les comptes professionnels, leurs producteurs, les coordonnées et notes saisies, les récoltes et les conseils. Chaque professionnel voit uniquement ses propres fiches. Les données sont enregistrées dans la base configurée par MONCACAO_DATABASE ; les exports et sauvegardes contiennent des données personnelles et doivent être protégés.

Le navigateur conserve seulement le cookie de session. Il ne stocke pas les fiches dans localStorage. Les nouvelles réponses sont marquées no-store ; le script retire les anciens caches nommés mon-cacao-* lorsqu'il les trouve. Les anciens comptes ou données localStorage ne sont pas effacés automatiquement, afin de permettre une reprise contrôlée.

Ce document décrit l'implémentation. Il ne constitue pas une politique juridique validée ni une attestation de conformité. L'organisation responsable doit définir avant ouverture la durée de conservation, les personnes habilitées et la procédure pour les demandes des personnes concernées.
