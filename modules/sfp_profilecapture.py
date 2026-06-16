# -------------------------------------------------------------------------------
# Name:         sfp_profilecapture
# Purpose:      Capture public profile images for visual comparison.
#
# Author:       bobpickettsr
#
# Created:      15/06/2026
# Copyright:    (c) bobpickettsr 2026
# Licence:      MIT
# -------------------------------------------------------------------------------

import json

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.profile_capture import (
    extract_url,
    finalize_capture,
    platform_from_url,
    profile_capture_from_account,
    venmo_capture_from_raw,
)


class sfp_profilecapture(SpiderFootPlugin):

    meta = {
        'name': "Profile Image Capture",
        'summary': "Download public profile photos from Venmo, Instagram, TikTok, and other account hits for visual comparison.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://www.spiderfoot.net/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [],
            'description': "Captures profile images from public account pages and APIs so investigators can compare faces and avatars across aliases.",
        }
    }

    opts = {
    }

    optdescs = {
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.__dataSource__ = "Profile Image Capture"
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["RAW_RIR_DATA", "ACCOUNT_EXTERNAL_OWNED", "SOCIAL_MEDIA"]

    def producedEvents(self):
        return ["RAW_RIR_DATA"]

    def _fetcher(self, url, timeout=None, useragent=None):
        return self.sf.fetchUrl(
            url,
            timeout=timeout or self.opts['_fetchtimeout'],
            useragent=useragent or self.opts['_useragent'],
        )

    def _emit_capture(self, record, event):
        evt = SpiderFootEvent(
            "RAW_RIR_DATA",
            json.dumps(record, ensure_ascii=False),
            self.__name__,
            event,
        )
        self.notifyListeners(evt)

    def handleEvent(self, event):
        if event.module == self.__name__:
            return

        event_name = event.eventType
        event_data = event.data
        scan_id = self.getScanId()

        try:
            scan = self.__sfdb__.scanInstanceGet(scan_id)
            scan_name = scan[0] if scan else scan_id
        except Exception:
            scan_name = scan_id

        record = None

        if event_name == "RAW_RIR_DATA" and event.module == "sfp_venmo":
            record = venmo_capture_from_raw(event_data, scan_id, scan_name)
        elif event_name in ("ACCOUNT_EXTERNAL_OWNED", "SOCIAL_MEDIA"):
            url = extract_url(event_data)
            platform = platform_from_url(url)
            record = profile_capture_from_account(url, scan_id, scan_name, platform)

        if not record:
            return

        cache_key = f"{scan_id}:{record.get('platform')}:{record.get('profile_url')}:{record.get('image_url')}"
        if cache_key in self.results:
            return

        self.results[cache_key] = True

        try:
            saved = finalize_capture(
                record,
                self._fetcher,
                timeout=self.opts['_fetchtimeout'],
                useragent=self.opts['_useragent'],
            )
        except Exception as e:
            self.debug(f"Profile capture failed for {record.get('profile_url')}: {e}")
            return

        if not saved:
            self.debug(f"No usable profile image for {record.get('profile_url')}")
            return

        self.info(
            f"Captured profile image for {saved.get('platform')} / "
            f"{saved.get('username') or saved.get('display_name') or saved.get('scan_name')}"
        )
        self._emit_capture(saved, event)