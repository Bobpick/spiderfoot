import pytest
import unittest

from modules.sfp_instagram import sfp_instagram
from sflib import SpiderFoot


@pytest.mark.usefixtures
class TestModuleInstagram(unittest.TestCase):

    def test_opts(self):
        module = sfp_instagram()
        self.assertEqual(len(module.opts), len(module.optdescs))

    def test_setup(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_instagram()
        module.setup(sf, dict())

    def test_watchedEvents_should_return_list(self):
        module = sfp_instagram()
        self.assertIsInstance(module.watchedEvents(), list)

    def test_producedEvents_should_return_list(self):
        module = sfp_instagram()
        self.assertIsInstance(module.producedEvents(), list)

    def test_username_from_social_media(self):
        module = sfp_instagram()
        event_data = "Instagram: <SFURL>https://www.instagram.com/example.user/</SFURL>"
        self.assertEqual(module._username_from_social_media(event_data), "example.user")