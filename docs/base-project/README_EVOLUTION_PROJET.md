> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# README Evolution du Projet (Chatbot-USMS)

## Objectif de ce document

Ce document resume :
- la base initiale du projet
- la migration SQLite vers PostgreSQL
- la nouvelle organisation des donnees partagees
- le workflow de dev actuel pour Windows et Linux

Derniere mise a jour : 2026-04-15
Branche de travail : `feature/postgres-migration`

---

## 1) Base initiale du projet

### Backend

- API FastAPI avec routes Auth, Chat et Admin
- Auth JWT avec roles utilisateur/admin
- persistance locale initiale en SQLite
- RAG FAQ via Qdrant + Groq
- gestion des conversations et de l'historique

### Frontend

- application Next.js
- pages login, chat, admin et profile
- internationalisation FR / EN / AR
- composant de rendu des emplois du temps

### Execution

- demarrage manuel backend + frontend
- script Windows `dev.ps1`
- environnement initial surtout oriente SQLite

---

## 2) Ce qui a ete ajoute avec la migration PostgreSQL

### A. Base PostgreSQL propre

- adoption d'une base PostgreSQL comme cible principale du projet
- unification de la couche DB dans `backend/services/db_service.py`
- compatibilite gardee pour la branche de demo SQLite
- correction des points qui cassaient sous PostgreSQL

### B. Migrations versionnees avec Alembic

- ajout de `backend/alembic.ini`
- ajout du dossier `backend/alembic/`
- premiere migration versionnee du schema
- compatibilite de bootstrap pour d'anciens schemas PostgreSQL sans metadata Alembic

### C. Strategie de partage des donnees utiles

- les FAQ restent des fichiers versionnes dans `backend/data/faq/`
- les emplois du temps sont maintenant partageables via `backend/data/seeds/timetables.json`
- un script exporte les EDT depuis SQLite
- un script recharge ces EDT dans PostgreSQL

### D. Scripts outilles pour le travail a deux

- `backend/scripts/export_timetables_seed.py`
- `backend/scripts/seed_timetables.py`
- `backend/scripts/rebuild_faq_index.py`
- `backend/scripts/bootstrap_dev_content.py`

Le script de bootstrap :
- initialise la base
- seed le compte admin
- importe les emplois du temps si la table est vide
- reconstruit la FAQ si Qdrant est vide

### E. Scripts de lancement simplifies

- `dev.ps1` pour Windows
- `dev.sh` pour Linux

Ces scripts :
- creent `.env` si besoin
- creent le `venv` si besoin
- installent les dependances manquantes
- demarrent `postgres`, `redis` et `qdrant`
- lancent le backend et le frontend en local

---

## 3) Conformité RGPD et Sécurité (Avril 2026)

Le projet a franchi une étape majeure en intégrant les principes de **Privacy by Design** et de **Conformité RGPD** :

### A. Droits des utilisateurs
- **Droit à l'effacement** : Suppression complète du compte et de l'historique depuis le profil.
- **Droit à la portabilité** : Export des données personnelles et de l'historique de chat au format JSON.
- **Transparence** : Affichage de scores de confiance (RAG confidence) et identification explicite de l'IA.

### B. Minimisation et protection technique
- **PII Masking** : Couche de protection automatisée qui masque les Emails et Numéros de téléphone avant l'envoi au cloud.
- **Truncature des prompts** : Limitation de la taille des données stockées en base.
- **Storage Limitation** : Purge automatique (et manuelle via admin) des conversations de plus de 180 jours.

### C. Durcissement de la sécurité
- **Politique de mots de passe** : Minimum 8 caractères, un chiffre et un caractère spécial.
- **Audit Logging** : Journalisation de toutes les actions critiques (connexion, export, suppression) pour l'accountability.

### D. Interface Moderne (UI/UX)
- Refonte complète de la page profil (Cards, Dashboard d'activité interactif).
- Internationalisation intégrale (FR/EN/AR) de toutes les nouvelles fonctionnalités.

---

## 4) Organisation Git retenue

- `main` : Branche stable intégrant PostgreSQL et la conformité RGPD.
- `sqlite-demo` / tag `v1-sqlite-demo` : Version historique avec SQLite.

---

## 5) État actuel du projet

- Le projet est entièrement conforme au RGPD ("Gold Standard").
- Le backend PostgreSQL est stable et versionné via Alembic.
- La suite de tests (64 tests) est intégralement passante sur la branche `main`.
- L'interface Next.js est modernisée et accessible.
- Le workflow Docker est validé et prêt pour la production.

---

## 6) Ce qui reste pertinent ensuite (Roadmap Sécurité)

### Court terme
- **Refresh Tokens** : Sécurisation avancée des sessions via HttpOnly cookies.
- **Account Lockout** : Protection contre les attaques par brute-force (blocage après 5 échecs).

### Moyen terme
- **Encryption at Rest** : Chiffrement des emails et données sensibles en base PostgreSQL.
- **IDOR Protection** : Durcissement de la validation de propriété des ressources (IDOR).
- **Accessibilité** : Audits continus WCAG 2.1.

---

## 6) Notes techniques

- `backend/vectorstore_qdrant/` ne constitue pas la source de verite partagee
- Qdrant peut etre reconstruit localement a partir des FAQ du repo
- la source de verite partagee pour le binome est maintenant :
  - `backend/data/faq/`
  - `backend/data/seeds/timetables.json`
- les comptes, conversations et messages restent locaux tant que vous n'utilisez pas une base distante commune
