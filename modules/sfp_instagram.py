# -------------------------------------------------------------------------------
# Name:         sfp_instagram
# Purpose:      Gather profile information from Instagram public pages.
#
# Author:       bobpickettsr
#
# Created:      15/06/2026
# Copyright:    (c) bobpickettsr 2026
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re

from spiderfoot import SpiderFootEvent, SpiderFootPlugin


class sfp_instagram(SpiderFootPlugin):

    meta = {
        'name': "Instagram",
        'summary': "Gather profile information from Instagram public pages.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://www.instagram.com/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [],
            'favIcon': "https://www.instagram.com/static/images/ico/favicon.ico",
            'logo': "https://www.instagram.com/static/images/ico/favicon.ico",
            'description': "Instagram is a photo and video sharing social networking service.",
        }
    }

    opts = {
    }

    optdescs = {
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.__dataSource__ = "Instagram"
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["USERNAME", "SOCIAL_MEDIA"]

    def producedEvents(self):
        return [
            "SOCIAL_MEDIA",
            "ACCOUNT_EXTERNAL_OWNED",
            "RAW_RIR_DATA",
        ]

    def _profile_url(self, username):
        return f"https://www.instagram.com/{username}/"

    def _query(self, username):
        url = self._profile_url(username)
        res = self.sf.fetchUrl(
            url,
            timeout=self.opts['_fetchtimeout'],
            useragent=self.opts['_useragent'],
        )

        if res['content'] is None:
            self.debug(f"No response from Instagram for {username}")
            return None

        html = res['content']

        title_match = re.search(r'<title>(.*?)</title>', html)
        title = title_match.group(1) if title_match else None

        bio_match = re.search(r'og:description" content="(.*?)"', html)
        bio = bio_match.group(1) if bio_match else None

        if "Sorry, this page isn't available" in html:
            status = "profile does not exist"
        elif "Login" in html and not bio:
            status = "blocked or restricted"
        elif title or bio:
            status = "profile detected"
        else:
            self.debug(f"No profile data parsed for Instagram user: {username}")
            return None

        return {
            "user": username,
            "url": url,
            "title": title,
            "bio": bio,
            "status": status,
        }

    def _emit_profile(self, profile, event):
        url = profile["url"]

        evt = SpiderFootEvent(
            "SOCIAL_MEDIA",
            f"Instagram: <SFURL>{url}</SFURL>",
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

        evt = SpiderFootEvent(
            "ACCOUNT_EXTERNAL_OWNED",
            f"Instagram (Category: Social Media)\n<SFURL>{url}</SFURL>",
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

    def _username_from_social_media(self, event_data):
        try:
            network = event_data.split(": ")[0]
            url = event_data.split(": ")[1].replace("<SFURL>", "").replace("</SFURL>", "")
        except Exception as e:
            self.debug(f"Unable to parse SOCIAL_MEDIA: {event_data} ({e})")
            return None

        if network != "Instagram":
            return None

        match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', url, re.IGNORECASE)
        if not match:
            return None

        return match.group(1).strip('.')

    def handleEvent(self, event):
        event_name = event.eventType
        src_module_name = event.module
        event_data = event.data

        self.debug(f"Received event, {event_name}, from {src_module_name}")

        username = None

        if event_name == "USERNAME":
            username = event_data.strip().lstrip("@")
        elif event_name == "SOCIAL_MEDIA":
            username = self._username_from_social_media(event_data)

        if not username:
            return

        cache_key = f"instagram:{username.lower()}"
        if cache_key in self.results:
            return

        self.results[cache_key] = True

        profile = self._query(username)
        if not profile:
            return

        if profile.get("status") == "profile does not exist":
            self.debug(f"Instagram profile does not exist: {username}")
            return

        self._emit_profile(profile, event)