from unittest.mock import patch

from django.test import SimpleTestCase

from recommendations.models import Place
from recommendations.services.ai_search_orchestrator import _order_by_distance


class DbRetrievalStrategyTests(SimpleTestCase):
    @patch("recommendations.services.ai_search_orchestrator.supports_postgis", return_value=True)
    def test_dense_cells_use_knn_and_sparse_cells_use_filtered_distance(self, _supports):
        dense_sql = str(_order_by_distance(Place.objects.all(), 35.1, 126.8, use_knn=True).query)
        sparse_sql = str(_order_by_distance(Place.objects.all(), 35.1, 126.8, use_knn=False).query)

        self.assertIn(" <-> ", dense_sql)
        self.assertIn("ST_Distance", sparse_sql)
        self.assertNotIn(" <-> ", sparse_sql)
