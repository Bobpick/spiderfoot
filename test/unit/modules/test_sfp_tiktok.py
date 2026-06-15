import pytest
import unittest

from modules.sfp_tiktok import sfp_tiktok
from sflib import SpiderFoot


@pytest.mark.usefixtures
class TestModuleTiktok(unittest.TestCase):

    def test_opts(self):
        module = sfp_tiktok()
        self.assertEqual(len(module.opts), len(module.optdescs))

    def test_setup(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_tiktok()
        module.setup(sf, dict())

    def test_watchedEvents_should_return_list(self):
        module = sfp_tiktok()
        self.assertIsInstance(module.watchedEvents(), list)

    def test_producedEvents_should_return_list(self):
        module = sfp_tiktok()
        self.assertIsInstance(module.producedEvents(), list)

    def test_instagram_usernames_from_bio(self):
        module = sfp_tiktok()
        bio = "DM on insta @cooluser or instagram.com/another.user"
        self.assertEqual(
            module._instagram_usernames_from_bio(bio),
            ["another.user", "cooluser"],
        )