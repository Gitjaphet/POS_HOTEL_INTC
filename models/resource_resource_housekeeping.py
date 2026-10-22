from odoo import api, fields, models


class ResourceResource(models.Model):
    """Bouton « Nettoyé » de la fiche chambre : visible tant que le ménage du
    jour (tâche en cours) n'est ni Propre ni Prêt. Champ non stocké, calculé
    à chaque lecture de la fiche."""
    _inherit = "resource.resource"

    x_hk_needs_cleaning = fields.Boolean(
        string="Ménage à faire",
        compute="_compute_x_hk_needs_cleaning",
    )

    @api.depends()
    def _compute_x_hk_needs_cleaning(self):
        clean = self._x_hk_clean_stages()
        for room in self:
            task = room.x_ongoing_task_id
            room.x_hk_needs_cleaning = bool(task) and task.stage_id not in clean
