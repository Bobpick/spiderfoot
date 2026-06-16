# -------------------------------------------------------------------------------
# Name:         sfp_cashapp
# Purpose:      Gather public Cash App profile information and avatar URLs.
#
# Author:       bobpickettsr
#
# Created:      15/06/2026
# Copyright:    (c) bobpickettsr 2026
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import time

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.profile_capture import (
    cashapp_capture_from_raw,
    cashapp_profile_from_html,
    cashapp_profile_url,
)


class sfp_cashapp(SpiderFootPlugin):

    meta = {
        'name': "Cash App",
        'summary': "Gather public Cash App cashtag profile information and avatar URLs.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://cash.app/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [],
            'favIcon': "https://cash-f.squarecdn.com/static/favicon.ico",
            'logo': "https://cash-f.squarecdn.com/static/favicon.ico",
            'description': "Cash App public cashtag pages expose display names and profile photos.",
        }
    }

    opts = {
    }

    optdescs = {
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.__dataSource__ = "Cash App"
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["USERNAME"]

    def producedEvents(self):
        return ["RAW_RIR_DATA", "HUMAN_NAME", "SOCIAL_MEDIA", "ACCOUNT_EXTERNAL_OWNED"]

    def _query(self, username: str):
        cashtag = username.lstrip("$").strip()
        if not cashtag:
            return None

        url = cashapp_profile_url(cashtag)
        res = self.sf.fetchUrl(
            url,
            timeout=self.opts['_fetchtimeout'],
            useragent=self.opts['_useragent'],
        )

        time.sleep(1)

        if res['content'] is None:
            self.debug(f"No response from Cash App for {cashtag}")
            return None

        profile = cashapp_profile_from_html(res['content'])
        if not profile:
            self.debug(f"No Cash App profile JSON for {cashtag}")
            return None

        profile["username"] = cashtag
        profile["profile_url"] = url
        return profile

    def _emit_profile(self, profile: dict, event):
        url = profile["profile_url"]
        display_name = profile.get("display_name") or profile.get("formatted_cashtag")

        if display_name and " " in display_name:
            evt = SpiderFootEvent("HUMAN_NAME", display_name, self.__name__, event)
            self.notifyListeners(evt)

        evt = SpiderFootEvent(
            "SOCIAL_MEDIA",
            f"Cash App: <SFURL>{url}</SFURL>",
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

        evt = SpiderFootEvent(
            "ACCOUNT_EXTERNAL_OWNED",
            f"Cash App (Category: finance)\n<SFURL>{url}</SFURL>",
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

        evt = SpiderFootEvent(
            "RAW_RIR_DATA",
            json.dumps(profile, ensure_ascii=False),
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

        capture = cashapp_capture_from_raw(
            json.dumps(profile, ensure_ascii=False),
            self.getScanId(),
            event.data,
        )
        if capture:
            self.info(
                f"Cash App profile photo found for {profile.get('formatted_cashtag')}: "
                f"{capture.get('image_url')}"
            )

    def handleEvent(self, event):
        event_name = event.eventType
        event_data = event.data

        if event_name != "USERNAME":
            return

        username = event_data.strip().lstrip("@")
        cache_key = username.lower()
        if cache_key in self.results:
            return

        self.results[cache_key] = True
        self.debug(f"Received event, {event_name}, from {event.module}")

        profile = self._query(username)
        if not profile:
            return

        self._emit_profile(profile, event)