# POS Hotel INTC

Module Odoo 19 de gestion hôtelière : transfert des consommations du point de vente vers la chambre, gestion du folio, enregistrement des occupants, fiche de police et clôture comptable quotidienne (night audit).

![Odoo 19](https://img.shields.io/badge/Odoo-19.0-714B67)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![License](https://img.shields.io/badge/License-LGPL--3-blue)

## Fonctionnalités

### Consommations POS vers la chambre
- Méthode de paiement **Chambre** dans le point de vente, avec une fenêtre de sélection du séjour à la caisse.
- Chaque consommation transférée devient une **charge de folio** rattachée au séjour (modèle `pos.hotel.folio.charge`).
- Annulation d'une commande avec **motif obligatoire**.

### Folio et facturation
- Règlement des charges dues d'un folio.
- Annulation d'un extra encore dû (motif obligatoire) et **remboursement** d'un extra déjà réglé.
- Ajout manuel d'extras et de services directement côté hôtel, hors POS.
- Paiements d'acompte, rapport de facture adapté, comptes comptables dédiés vérifiés à l'installation.

### Séjours et chambres
- Enregistrement (check-in) et départ **par chambre**.
- Ajout, changement et retrait de chambre sur une réservation confirmée, avec **historique** des modifications.
- Dérogation de check-out en cas de solde impayé.
- Sources de réservation prêtes à l'emploi : Booking.com, site web, contact direct, walk-in, agence.

### Occupants et fiche de police
- Enregistrement des occupants d'un séjour (`pos.hotel.stay.guest`).
- Règles configurables par société : portée des occupants à enregistrer, comportement si les informations sont incomplètes à l'arrivée, champs obligatoires (nationalité, pièce d'identité, date de naissance, provenance/destination).
- **Fiche de police en PDF** avec déclaration signée par le client (texte configurable).

### Planning
- Vue Gantt des chambres personnalisée (statistiques hôtel, titres, couleurs et hauteur des lignes).
- Formulaire de créneau de planning adapté aux séjours.

### Night audit
- Clôture et **rapprochement comptable** d'une journée d'exploitation, avec journal d'exécution et séquence dédiée.

## Prérequis

| Élément | Détail |
|---|---|
| Odoo | 19.0 |
| Modules requis | `point_of_sale`, `hotel`, `planning` |
| Python | Version compatible avec Odoo 19 (le CI s'exécute en 3.11) |

Le module `planning` fait partie d'Odoo Enterprise. Le module `hotel` correspond à l'industrie Hôtel d'Odoo : vérifiez sa disponibilité dans votre édition.

## Installation

```bash
# 1. Cloner le module dans le dossier des addons personnalisés
cd /chemin/vers/vos/addons
git clone https://github.com/Gitjaphet/POS_HOTEL_INTC.git

# 2. Ajouter ce dossier à addons_path dans odoo.conf, puis redémarrer Odoo

# 3. Installer le module (ou depuis Applications, après mise à jour de la liste)
python odoo-bin -c odoo.conf -d <base> -i POS_HOTEL_INTC --stop-after-init
```

À l'installation, un `post_init_hook` crée ou vérifie la méthode de paiement Chambre et les comptes associés, et aligne les calendriers de chambres ainsi que la vue du formulaire de réservation.

## Configuration

Dans **Réglages**, section Hôtel :
- Occupants à enregistrer et comportement si les informations sont incomplètes à l'arrivée.
- Champs obligatoires pour les occupants.
- Texte de la déclaration en pied de fiche de police.

Les sources de réservation se gèrent dans les sources UTM (données chargées en `noupdate` : vos renommages sont conservés lors des mises à jour).

## Structure du dépôt

```
POS_HOTEL_INTC/
├── models/        Modèles métier (folio, night audit, occupants, POS, planning…)
├── wizards/       Assistants (check-in, chambres, règlement, annulation, remboursement…)
├── views/         Vues XML (réservation, partenaire, paramètres, night audit, planning…)
├── report/        Fiche de police (PDF)
├── security/      Droits d'accès
├── data/          Sources de réservation, séquence night audit
├── migrations/    Scripts post-migration, un par version
├── static/src/    POS (OWL), vue Gantt, styles SCSS
├── tests/         Tests Odoo
├── hooks.py       post_init_hook
└── .github/workflows/deploy.yml
```

## Tests

```bash
python odoo-bin -c odoo.conf -d <base_de_test> -i POS_HOTEL_INTC \
    --test-enable --test-tags /POS_HOTEL_INTC --stop-after-init
```

Les tests actuels couvrent les transitions d'état des charges de folio (annulation, remboursement, règlement).

## Intégration et déploiement continus

Le workflow GitHub Actions (`deploy.yml`) s'exécute à chaque push sur `main` :

1. **test** : vérification de syntaxe Python (`compileall`) et analyse `pyflakes`.
2. **build** : validation du `__manifest__.py` (clés `name` et `version`).
3. **deploy** : mise à jour du code sur le VPS par SSH, arrêt d'Odoo, mise à jour du module (`-u POS_HOTEL_INTC`), puis redémarrage. **En cas d'échec** de la mise à jour, le code revient automatiquement au commit précédent et Odoo est redémarré.

Les accès au serveur sont stockés dans les secrets GitHub (`VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_SSH_KEY`).

## Versions

La version courante est indiquée dans `__manifest__.py`. Chaque évolution de schéma s'accompagne d'un script dans `migrations/<version>/`.

## Auteur

**Japhet Valeureux BEZANAKA**, développeur full-stack Python et consultant Odoo, INTC Madagascar.

- Portfolio : https://japhet.medevstack.com/
- GitHub : https://github.com/Gitjaphet/
- LinkedIn : https://www.linkedin.com/in/japhet-bezanaka-dev/

## Licence

LGPL-3
