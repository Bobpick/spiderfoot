# -*- coding: utf-8 -*-
"""Download and compare public profile images across SpiderFoot scans."""

import ast
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse

CAPTURES_DIR = Path(__file__).resolve().parents[1] / "captures"

PLACEHOLDER_MARKERS = (
    "no-image",
    "no_image",
    "noimage",
    "default-avatar",
    "default_avatar",
    "placeholder",
    "anonymous",
    "blank.gif",
    "blank.png",
    "avatar-default",
    "static/images/default",
    "guest.png",
    "user.png",
    "profile-pic-default",
    "default_profile",
)

HIGH_VALUE_PLATFORMS = (
    "venmo",
    "cashapp",
    "instagram",
    "tiktok",
    "github",
    "twitter",
    "x.com",
    "facebook",
    "cash.app",
    "paypal",
    "snapchat",
    "linkedin",
)

PHASH_MATCH_THRESHOLD = 12
MAX_CAPTURES_PER_ANALYSIS = 40


def captures_root() -> Path:
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    return CAPTURES_DIR


def is_placeholder_image(url: str) -> bool:
    if not url:
        return True
    blob = url.lower()
    return any(marker in blob for marker in PLACEHOLDER_MARKERS)


def safe_slug(value: str, limit: int = 60) -> str:
    value = re.sub(r"[^\w.\-]+", "_", (value or "").strip().lower())
    return (value[:limit] or "unknown").strip("_")


def extract_url(data: str) -> str:
    data = data.replace("<SFURL>", "").replace("</SFURL>", "")
    match = re.search(r"https?://[^\s<>']+", data)
    return match.group(0).rstrip("/") if match else ""


def platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    if "venmo" in host:
        return "venmo"
    if "instagram" in host:
        return "instagram"
    if "tiktok" in host:
        return "tiktok"
    if "github" in host:
        return "github"
    if "twitter" in host or host == "x.com":
        return "twitter"
    if "facebook" in host:
        return "facebook"
    if "cash.app" in host:
        return "cashapp"
    return host.split(":")[0] or "unknown"


def parse_event_blob(data: str) -> dict:
    data = data.strip()
    if not data:
        return {}

    if data.startswith("{") and data.endswith("}"):
        try:
            return json.loads(data.replace("'", '"'))
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(data)
            if isinstance(parsed, dict):
                return parsed
        except (SyntaxError, ValueError):
            pass

    return {}


def cashapp_profile_url(username: str) -> str:
    cashtag = (username or "").lstrip("$").strip()
    return f"https://cash.app/${cashtag}"


def cashapp_username_from_url(url: str) -> str:
    match = re.search(r"cash\.app/\$?([A-Za-z0-9_\-]+)", url or "", re.IGNORECASE)
    return match.group(1) if match else ""


def cashapp_profile_from_html(html: str) -> dict:
    if not html:
        return None

    match = re.search(r"var profile\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def cashapp_avatar_url(profile: dict) -> str:
    if not isinstance(profile, dict):
        return ""
    avatar = profile.get("avatar") or {}
    if isinstance(avatar, dict):
        return (avatar.get("image_url") or "").strip()
    return ""


def is_cashapp_placeholder(profile: dict) -> bool:
    image_url = cashapp_avatar_url(profile)
    if not image_url:
        return True
    return is_placeholder_image(image_url)


def cashapp_capture_from_raw(data: str, scan_id: str, scan_name: str) -> dict:
    payload = parse_event_blob(data)
    image_url = payload.get("image_url") or cashapp_avatar_url(payload)
    if not image_url or is_placeholder_image(image_url):
        return None

    username = (
        payload.get("username")
        or cashapp_username_from_url(payload.get("profile_url", ""))
        or scan_name
    )
    profile_url = payload.get("profile_url") or cashapp_profile_url(username)

    return {
        "platform": "cashapp",
        "username": username,
        "display_name": payload.get("display_name"),
        "profile_url": profile_url,
        "image_url": image_url,
        "scan_id": scan_id,
        "scan_name": scan_name,
        "source_module": "sfp_cashapp",
    }


def venmo_capture_from_raw(data: str, scan_id: str, scan_name: str) -> dict:
    payload = parse_event_blob(data)
    image_url = payload.get("profile_picture_url") or payload.get("profilePictureUrl")
    if not image_url or is_placeholder_image(image_url):
        return None

    username = payload.get("username") or payload.get("display_name") or scan_name
    profile_url = f"https://account.venmo.com/u/{username}" if username else extract_url(data)

    return {
        "platform": "venmo",
        "username": username,
        "display_name": payload.get("display_name"),
        "profile_url": profile_url,
        "image_url": image_url.rstrip("',"),
        "scan_id": scan_id,
        "scan_name": scan_name,
        "source_module": "sfp_venmo",
    }


def extract_og_image(html: str) -> str:
    if not html:
        return ""

    patterns = (
        r'property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
        r'name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def profile_capture_from_account(url: str, scan_id: str, scan_name: str, platform: str = "") -> dict:
    if not url:
        return None

    platform = platform or platform_from_url(url)
    if platform not in HIGH_VALUE_PLATFORMS:
        return None

    record = {
        "platform": platform,
        "profile_url": url,
        "image_url": None,
        "scan_id": scan_id,
        "scan_name": scan_name,
        "source_module": "sfp_profilecapture",
    }

    if platform == "cashapp":
        username = cashapp_username_from_url(url)
        record["username"] = username or scan_name

    return record


def _image_from_bytes(content: bytes):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for profile image comparison. pip install Pillow") from exc

    return Image.open(io.BytesIO(content))


def compute_phash_hex(content: bytes) -> str:
    image = _image_from_bytes(content).convert("L").resize((8, 8))
    pixels = list(image.getdata())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def hamming_distance_hex(left: str, right: str) -> int:
    if not left or not right:
        return 64
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def download_image(fetcher, image_url: str, timeout: int = 15, useragent: str = "") -> bytes:
    if not image_url or is_placeholder_image(image_url):
        return None

    result = fetcher(
        image_url,
        timeout=timeout,
        useragent=useragent,
    )
    content = result.get("content") if isinstance(result, dict) else None
    if not content:
        return None

    if isinstance(content, str):
        content = content.encode("utf-8", errors="ignore")

    if len(content) < 256:
        return None

    return content


def save_capture(record: dict, content: bytes, root: Path = None) -> dict:
    root = root or captures_root()
    scan_id = safe_slug(record.get("scan_id") or "unknown")
    platform = safe_slug(record.get("platform") or "site")
    username = safe_slug(record.get("username") or record.get("display_name") or "profile")

    digest = hashlib.sha1(content).hexdigest()[:10]
    filename = f"{platform}_{username}_{digest}.jpg"
    scan_dir = root / scan_id
    scan_dir.mkdir(parents=True, exist_ok=True)
    filepath = scan_dir / filename
    filepath.write_bytes(content)

    phash = compute_phash_hex(content)
    web_path = f"/captures/{scan_id}/{filename}"

    saved = {
        **record,
        "type": "profile_capture",
        "filename": filename,
        "local_path": str(filepath),
        "web_path": web_path,
        "phash": phash,
        "sha1": hashlib.sha1(content).hexdigest(),
        "bytes": len(content),
    }
    return saved


def collect_capture_candidates(events: list) -> list:
    candidates = []
    seen = set()

    for item in events:
        event_type = item.get("type")
        data = item.get("data", "")
        scan_id = item.get("scan_id", "")
        scan_name = item.get("scan_name", "")
        module = item.get("module", "")
        key_base = f"{scan_id}:{event_type}:{data[:120]}"

        if key_base in seen:
            continue

        record = None
        if event_type == "RAW_RIR_DATA" and (
            module == "sfp_cashapp" or '"avatar"' in data or "'avatar'" in data
        ):
            record = cashapp_capture_from_raw(data, scan_id, scan_name)
        elif event_type == "RAW_RIR_DATA" and (
            module == "sfp_venmo" or "profile_picture_url" in data
        ):
            record = venmo_capture_from_raw(data, scan_id, scan_name)
        elif event_type == "RAW_RIR_DATA" and '"type": "profile_capture"' in data:
            try:
                record = json.loads(data)
            except json.JSONDecodeError:
                record = None
        elif event_type in ("ACCOUNT_EXTERNAL_OWNED", "SOCIAL_MEDIA"):
            url = item.get("url") or extract_url(data)
            platform = item.get("platform") or platform_from_url(url)
            record = profile_capture_from_account(url, scan_id, scan_name, platform)

        if record and (record.get("image_url") or record.get("profile_url")):
            seen.add(key_base)
            candidates.append(record)

    return candidates


def finalize_capture(record: dict, fetcher, timeout: int = 15, useragent: str = "") -> dict:
    image_url = record.get("image_url")

    if not image_url and record.get("profile_url"):
        page = fetcher(record["profile_url"], timeout=timeout, useragent=useragent)
        html = page.get("content") if isinstance(page, dict) else None
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="ignore")
        if (record.get("platform") or "") == "cashapp":
            profile = cashapp_profile_from_html(html or "")
            if profile:
                record["display_name"] = profile.get("display_name") or record.get("display_name")
                image_url = cashapp_avatar_url(profile)
        else:
            image_url = extract_og_image(html or "")
        record["image_url"] = image_url

    if not image_url or is_placeholder_image(image_url):
        return None

    content = download_image(fetcher, image_url, timeout=timeout, useragent=useragent)
    if not content:
        return None

    return save_capture(record, content)


def find_visual_matches(captures: list, threshold: int = PHASH_MATCH_THRESHOLD) -> list:
    matches = []
    valid = [
        cap for cap in captures
        if cap.get("phash") and not is_placeholder_image(cap.get("image_url") or "captured")
    ]

    for i, left in enumerate(valid):
        for right in valid[i + 1:]:
            if left.get("sha1") == right.get("sha1"):
                distance = 0
            else:
                distance = hamming_distance_hex(left.get("phash"), right.get("phash"))

            if distance <= threshold:
                confidence = "high" if distance <= 5 else "medium" if distance <= 10 else "low"
                matches.append({
                    "distance": distance,
                    "confidence": confidence,
                    "left": {
                        "scan_name": left.get("scan_name"),
                        "platform": left.get("platform"),
                        "profile_url": left.get("profile_url"),
                        "web_path": left.get("web_path"),
                        "display_name": left.get("display_name"),
                    },
                    "right": {
                        "scan_name": right.get("scan_name"),
                        "platform": right.get("platform"),
                        "profile_url": right.get("profile_url"),
                        "web_path": right.get("web_path"),
                        "display_name": right.get("display_name"),
                    },
                })

    matches.sort(key=lambda item: item["distance"])
    return matches


def render_visual_comparison_markdown(captures: list, matches: list) -> str:
    if not captures:
        return ""

    lines = [
        "## Visual Profile Comparison",
        "",
        f"Captured {len(captures)} usable profile image(s). "
        f"Found {len(matches)} possible visual match(es) across scans.",
        "",
    ]

    if matches:
        lines.append("### Likely Visual Matches")
        lines.append("")
        for match in matches[:20]:
            left = match["left"]
            right = match["right"]
            lines.append(
                f"- **{match['confidence']}** (distance {match['distance']}): "
                f"{left['scan_name']} / {left['platform']} vs "
                f"{right['scan_name']} / {right['platform']}"
            )
        lines.append("")

    lines.append("### Captured Images")
    lines.append("")
    for cap in captures:
        label = cap.get("display_name") or cap.get("username") or cap.get("scan_name")
        lines.append(
            f"- {cap.get('scan_name')} / {cap.get('platform')} / {label}: "
            f"{cap.get('profile_url')} ([image]({cap.get('web_path')}))"
        )
    lines.append("")
    return "\n".join(lines)