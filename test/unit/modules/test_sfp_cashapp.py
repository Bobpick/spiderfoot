import unittest

from modules.sfp_cashapp import sfp_cashapp
from sflib import SpiderFoot
from spiderfoot.profile_capture import cashapp_capture_from_raw, cashapp_profile_from_html


class TestModuleCashApp(unittest.TestCase):

    def test_opts(self):
        module = sfp_cashapp()
        self.assertEqual(len(module.opts), len(module.optdescs))

    def test_setup(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_cashapp()
        module.setup(sf, dict())

    def test_watchedEvents_should_return_list(self):
        module = sfp_cashapp()
        self.assertIn("USERNAME", module.watchedEvents())

    def test_producedEvents_should_return_list(self):
        module = sfp_cashapp()
        self.assertIn("RAW_RIR_DATA", module.producedEvents())

    def test_cashapp_profile_from_html(self):
        html = """
        var profile = {"display_name":"Luke Test","formatted_cashtag":"$luke",
        "avatar":{"image_url":"https://franklin-assets.s3.amazonaws.com/apps/imgs/example.jpeg","initial":"L"}};
        """
        profile = cashapp_profile_from_html(html)
        self.assertEqual(profile["display_name"], "Luke Test")
        self.assertIn("example.jpeg", profile["avatar"]["image_url"])

    def test_cashapp_capture_skips_initial_only_avatar(self):
        raw = (
            '{"display_name":"Lucas Simmons","formatted_cashtag":"$itsluke7",'
            '"avatar":{"initial":"L"}, "username":"itsluke7", '
            '"profile_url":"https://cash.app/$itsluke7"}'
        )
        self.assertIsNone(cashapp_capture_from_raw(raw, "ABC", "ItsLuke7"))