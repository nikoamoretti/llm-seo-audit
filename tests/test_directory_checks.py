import os
import unittest
from unittest.mock import Mock, patch

from web_presence import WebPresenceChecker


class DirectoryChecksTest(unittest.TestCase):
    def setUp(self):
        self.checker = WebPresenceChecker()

    @patch.dict(
        os.environ,
        {"YELP_API_KEY": "yelp-test-key", "GOOGLE_PLACES_API_KEY": "google-test-key"},
        clear=False,
    )
    @patch("web_presence.requests.get")
    def test_directory_checks_use_api_results_and_extract_metadata(self, mock_get):
        yelp_response = Mock(status_code=200)
        yelp_response.json.return_value = {
            "businesses": [
                {
                    "name": "Laveta Coffee Roasters",
                    "rating": 4.6,
                    "review_count": 416,
                    "url": "https://www.yelp.com/biz/laveta-coffee-roasters-los-angeles",
                }
            ]
        }
        google_response = Mock(status_code=200)
        google_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "name": "Laveta Coffee Roasters",
                    "rating": 4.7,
                    "user_ratings_total": 987,
                    "place_id": "place-123",
                }
            ],
        }
        mock_get.side_effect = [yelp_response, google_response]

        results = self.checker._check_directories("Laveta", "Echo Park, Los Angeles")

        self.assertTrue(results["yelp_found"])
        self.assertEqual(results["yelp_rating"], 4.6)
        self.assertEqual(results["yelp_review_count"], 416)
        self.assertEqual(
            results["yelp_url"],
            "https://www.yelp.com/biz/laveta-coffee-roasters-los-angeles",
        )
        self.assertTrue(results["google_business_found"])
        self.assertEqual(results["google_rating"], 4.7)
        self.assertEqual(results["google_review_count"], 987)
        self.assertEqual(results["google_place_id"], "place-123")

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(
            mock_get.call_args_list[0].args[0],
            "https://api.yelp.com/v3/businesses/search",
        )
        self.assertEqual(
            mock_get.call_args_list[1].args[0],
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
        )

    @patch.dict(
        os.environ,
        {"YELP_API_KEY": "yelp-test-key", "GOOGLE_PLACES_API_KEY": "google-test-key"},
        clear=False,
    )
    @patch("web_presence.requests.get")
    def test_directory_checks_return_false_on_confirmed_non_match(self, mock_get):
        yelp_response = Mock(status_code=200)
        yelp_response.json.return_value = {
            "businesses": [{"name": "Different Cafe", "rating": 4.2, "review_count": 25}]
        }
        google_response = Mock(status_code=200)
        google_response.json.return_value = {"status": "ZERO_RESULTS", "results": []}
        mock_get.side_effect = [yelp_response, google_response]

        results = self.checker._check_directories("Laveta", "Echo Park, Los Angeles")

        self.assertFalse(results["yelp_found"])
        self.assertFalse(results["google_business_found"])
        self.assertIsNone(results["yelp_rating"])
        self.assertIsNone(results["google_rating"])

    @patch.dict(os.environ, {}, clear=True)
    def test_directory_checks_warn_and_leave_values_unchecked_when_keys_missing(self):
        with self.assertLogs("web_presence", level="WARNING") as logs:
            results = self.checker._check_directories("Laveta", "Echo Park, Los Angeles")

        self.assertIsNone(results["yelp_found"])
        self.assertIsNone(results["google_business_found"])
        self.assertIn("YELP_API_KEY is not set", "\n".join(logs.output))
        self.assertIn("GOOGLE_PLACES_API_KEY is not set", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
