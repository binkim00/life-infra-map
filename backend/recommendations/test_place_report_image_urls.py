from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from recommendations.serializers import PlaceReportImageSerializer


class PlaceReportImageUrlTests(SimpleTestCase):
    @override_settings(
        FILE_STORAGE_BACKEND="s3",
        AWS_STORAGE_BUCKET_NAME="life-infra-map-media",
    )
    def test_public_url_does_not_expose_internal_storage_endpoint(self):
        image = SimpleNamespace(
            name="place_reports/2026/09/photo 1.png",
            url="http://100.71.169.91/life-infra-map-media/place_reports/2026/09/photo%201.png",
        )
        report_image = SimpleNamespace(image=image)

        request = RequestFactory().get("/api/recommendations/place-reports/14/", secure=True, HTTP_HOST="yeogiljido.com")

        with patch.dict("os.environ", {"PUBLIC_MEDIA_BASE_URL": "https://yeogiljido.com/media/"}):
            self.assertEqual(
                PlaceReportImageSerializer(context={"request": request}).get_image_url(report_image),
                "https://yeogiljido.com/media/life-infra-map-media/place_reports/2026/09/photo%201.png",
            )
