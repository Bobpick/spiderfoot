import json
import unittest

from modules.sfp_profilecapture import sfp_profilecapture
from sflib import SpiderFoot
from spiderfoot.profile_capture import (
    is_placeholder_image,
    parse_event_blob,
    venmo_capture_from_raw,
)


class TestModuleProfileCapture(unittest.TestCase):

    def test_opts(self):
        module = sfp_profilecapture()
        self.assertEqual(len(module.opts), len(module.optdescs))

    def test_setup(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_profilecapture()
        module.setup(sf, dict())

    def test_watchedEvents_should_return_list(self):
        module = sfp_profilecapture()
        self.assertIsInstance(module.watchedEvents(), list)

    def test_producedEvents_should_return_list(self):
        module = sfp_profilecapture()
        self.assertIsInstance(module.producedEvents(), list)

    def test_placeholder_detection(self):
        self.assertTrue(is_placeholder_image("https://s3.amazonaws.com/venmo/no-image.gif"))
        self.assertTrue(is_placeholder_image("https://example.com/default-avatar.png"))
        self.assertFalse(is_placeholder_image("https://pics-v3.venmo.com/abc?width=460"))

    def test_venmo_capture_from_raw(self):
        raw = (
            "{'date_joined': '2020', 'profile_picture_url': "
            "'https://pics-v3.venmo.com/88952088-1fdd-4af2-8fbf-3258835ced60?width=460', "
            "'username': 'ItsLuke7', 'display_name': 'Luke C'}"
        )
        record = venmo_capture_from_raw(raw, "ABC123", "ItsLuke7")
        self.assertEqual(record["platform"], "venmo")
        self.assertEqual(record["username"], "ItsLuke7")
        self.assertIn("pics-v3.venmo.com", record["image_url"])

    def test_venmo_no_image_skipped(self):
        raw = (
            "{'profile_picture_url': 'https://s3.amazonaws.com/venmo/no-image.gif', "
            "'username': 'lukechan', 'display_name': 'Luke Chan'}"
        )
        self.assertIsNone(venmo_capture_from_raw(raw, "ABC123", "Luke Chan"))

    def test_parse_event_blob_json(self):
        payload = parse_event_blob('{"profile_picture_url": "https://example.com/a.jpg"}')
        self.assertEqual(payload["profile_picture_url"], "https://example.com/a.jpg")