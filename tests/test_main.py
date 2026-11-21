import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.cache import Cache
from app.main import app, location_matches


class TestRadarAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_root_route_runs(self) -> None:
        response = TestClient(app).get("/")

        self.assertIn(response.status_code, (307, 200))

    def test_stats_route_runs(self) -> None:
        response = TestClient(app).get("/api/stats")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("counters", body)
        self.assertIn("cache_only", body)

    def test_radar_returns_validation_error_for_invalid_profile(self) -> None:
        response = TestClient(app).post("/api/radar", json={"role": ""})

        self.assertEqual(response.status_code, 422)

    def test_static_page_is_served(self) -> None:
        response = TestClient(app).get("/static/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Internship Radar", response.text)

    def test_saved_postings_route_runs(self) -> None:
        response = TestClient(app).get("/api/postings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("postings", response.json())

    def test_location_gate_rejects_other_countries(self) -> None:
        self.assertTrue(location_matches("Finland", "Helsinki, Finland"))
        self.assertTrue(location_matches("Finland", "Remote - Finland"))
        self.assertFalse(location_matches("Finland", "Kaunas, Lithuania"))
