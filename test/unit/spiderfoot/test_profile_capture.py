import unittest

from spiderfoot.profile_capture import (
    cashapp_capture_from_raw,
    find_visual_matches,
    is_placeholder_image,
    venmo_capture_from_raw,
)


class TestProfileCapture(unittest.TestCase):

    def test_find_visual_matches_exact_sha(self):
        captures = [
            {
                "scan_name": "Scan A",
                "platform": "venmo",
                "profile_url": "https://account.venmo.com/u/a",
                "web_path": "/captures/a/venmo_a.jpg",
                "phash": "0000000000000000",
                "sha1": "abc",
            },
            {
                "scan_name": "Scan B",
                "platform": "venmo",
                "profile_url": "https://account.venmo.com/u/b",
                "web_path": "/captures/b/venmo_b.jpg",
                "phash": "0000000000000000",
                "sha1": "abc",
            },
        ]
        matches = find_visual_matches(captures)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["distance"], 0)

    def test_cashapp_capture_from_raw(self):
        raw = (
            '{"display_name":"Lucas Mcmurray","formatted_cashtag":"$luke",'
            '"avatar":{"image_url":"https://franklin-assets.s3.amazonaws.com/apps/imgs/waSwYlODwxvq5SsJ92G2o.jpeg"},'
            '"username":"luke","profile_url":"https://cash.app/$luke"}'
        )
        record = cashapp_capture_from_raw(raw, "ABC", "luke")
        self.assertEqual(record["platform"], "cashapp")
        self.assertIn("franklin-assets", record["image_url"])

    def test_placeholder_skips_match(self):
        captures = [
            {
                "scan_name": "Scan A",
                "platform": "venmo",
                "image_url": "https://s3.amazonaws.com/venmo/no-image.gif",
                "web_path": "/captures/a/venmo_a.jpg",
                "phash": "0000000000000000",
                "sha1": "abc",
            }
        ]
        self.assertEqual(find_visual_matches(captures), [])