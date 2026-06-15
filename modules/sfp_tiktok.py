# -------------------------------------------------------------------------------
# Name:         sfp_tiktok
# Purpose:      Gather profile information from TikTok public pages.
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


class sfp_tiktok(SpiderFootPlugin):

    meta = {
        'name': "TikTok",
        'summary': "Gather profile information from TikTok public pages.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://www.tiktok.com/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [],
            'favIcon': "https://www.tiktok.com/favicon.ico",
            'logo': "https://www.tiktok.com/favicon.ico",
            'description': "TikTok is a short-form video hosting service.",
        }
    }

    opts = {
    }

    optdescs = {
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.__dataSource__ = "TikTok"
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
            "USERNAME",
        ]

    def _extract(self, text, regex):
        match = re.search(regex, text)
        return match.group(1) if match else None

    def _safe_int(self, value):
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def _instagram_usernames_from_bio(self, bio):
        if not bio:
            return []

        found = set()

        for match in re.findall(r'instagram\.com/([a-zA-Z0-9_.]+)', bio, re.IGNORECASE):
            found.add(match.strip('.'))

        for match in re.findall(r'@([a-zA-Z0-9_.]{2,30})', bio):
            if 'insta' in bio.lower():
                found.add(match)

        return sorted(found)

    def _profile_url(self, username):
        return f"https://www.tiktok.com/@{username}"

    def _query(self, username):
        url = self._profile_url(username)
        res = self.sf.fetchUrl(
            url,
            timeout=self.opts['_fetchtimeout'],
            useragent=self.opts['_useragent'],
        )

        if res['content'] is None:
            self.debug(f"No response from TikTok for {username}")
            return None

        if res['code'] != "200":
            self.debug(f"TikTok profile not found or blocked: {username}")
            return None

        text = res['content']
        nickname = self._extract(text, r'"nickname":"(.*?)"')
        bio = self._extract(text, r'"signature":"(.*?)"')

        if bio:
            bio = bio.replace("\\n", "\n")

        profile = {
            "user": username,
            "url": url,
            "nickname": nickname,
            "bio": bio,
            "followers": self._safe_int(self._extract(text, r'"followerCount":(.*?),')),
            "following": self._safe_int(self._extract(text, r'"followingCount":(.*?),')),
            "likes": self._safe_int(self._extract(text, r'"heartCount":(.*?),')),
            "videos": self._safe_int(self._extract(text, r'"videoCount":(.*?),')),
            "verified": self._extract(text, r'"verified":(true|false)'),
        }

        if not nickname and not bio:
            self.debug(f"No profile data parsed for TikTok user: {username}")
            return None

        return profile

    def _emit_profile(self, profile, event):
        username = profile["user"]
        url = profile["url"]

        evt = SpiderFootEvent(
            "SOCIAL_MEDIA",
            f"TikTok: <SFURL>{url}</SFURL>",
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

        evt = SpiderFootEvent(
            "ACCOUNT_EXTERNAL_OWNED",
            f"TikTok (Category: Social Media)\n<SFURL>{url}</SFURL>",
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

        for insta_user in self._instagram_usernames_from_bio(profile.get("bio")):
            if insta_user == username:
                continue

            insta_url = f"https://www.instagram.com/{insta_user}/"
            evt = SpiderFootEvent("USERNAME", insta_user, self.__name__, event)
            self.notifyListeners(evt)

            evt = SpiderFootEvent(
                "SOCIAL_MEDIA",
                f"Instagram: <SFURL>{insta_url}</SFURL>",
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

        if network != "TikTok":
            return None

        match = re.search(r'tiktok\.com/@([a-zA-Z0-9_.]+)', url, re.IGNORECASE)
        if not match:
            return None

        return match.group(1)

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

        cache_key = f"tiktok:{username.lower()}"
        if cache_key in self.results:
            return

        self.results[cache_key] = True

        profile = self._query(username)
        if not profile:
            return

        self._emit_profile(profile, event)