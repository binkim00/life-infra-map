from recommendations.management.commands.export_identity_evidence_validation_set import stratified
from django.test import SimpleTestCase


class ValidationSetTests(SimpleTestCase):
    def test_stratified_selection_keeps_multiple_groups(self):
        rows = [
            {"group": "a", "id": 1}, {"group": "a", "id": 2},
            {"group": "b", "id": 3}, {"group": "b", "id": 4},
        ]
        selected = stratified(rows, 3, key=lambda row: row["group"])
        self.assertEqual({row["group"] for row in selected}, {"a", "b"})
