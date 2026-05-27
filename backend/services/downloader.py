"""Instagram reel extractor and downloader.

Approach: scrape the public reel HTML, parse the embedded JSON blob that
Instagram ships in a <script type="application/json"> tag, then pull the
audio-only stream URL out of the DASH manifest also embedded in that JSON.

We deliberately avoid yt-dlp here. yt-dlp's Instagram extractor does not
reliably surface caption/hashtag/music metadata, and we want all that data
in a single pass.

Public surface:
    download_reel(url, reel_id, download_video=False) -> DownloadResult
    DownloadResult, ReelMetadata, ReelUser, MusicInfo, VideoVersion, ImageVersion
    DownloadError (with is_retryable flag matching the existing pipeline contract)
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import urlparse

from curl_cffi import requests as cffi_requests
from parsel import Selector

logger = logging.getLogger(__name__)

# DASH MPD namespace — Instagram uses the standard schema
_MPD_NS = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}

# Possible spellings of the items-bearing key in Instagram's GraphQL response.
# IG has shipped both single- and double-underscore variants between
# `shortcode` and `web_info`; we try both.
_SHORTCODE_INFO_KEYS = (
    "xdt_api__v1__media__shortcode__web_info",
    "xdt_api__v1__media__shortcode_web_info",
)

_HASHTAG_RE = re.compile(r"#([\w_]+)", re.UNICODE)
_MENTION_RE = re.compile(r"@([\w.]+)", re.UNICODE)
_DURATION_RE = re.compile(r"PT([\d.]+)S")


# ---------------------------------------------------------------------------
# Data classes — what the caller gets back
# ---------------------------------------------------------------------------


@dataclass
class ReelUser:
    pk: str
    username: str
    full_name: str | None
    profile_pic_url: str | None
    is_private: bool
    is_verified: bool
    is_embeds_disabled: bool | None = None


@dataclass
class MusicInfo:
    audio_type: str | None  # "licensed_music" | "original_sounds" | etc.
    title: str | None
    artist: str | None
    audio_cluster_id: str | None
    is_explicit: bool | None
    is_trending_in_clips: bool | None = None
    should_mute_audio: bool = False
    should_mute_audio_reason: str | None = None


@dataclass
class VideoVersion:
    width: int
    height: int
    url: str
    type: int


@dataclass
class ImageVersion:
    width: int
    height: int
    url: str


@dataclass
class ReelMetadata:
    # Identifiers
    shortcode: str
    pk: str
    media_id: str

    # Author
    user: ReelUser
    creator_handle: str

    # Content
    caption: str | None
    caption_created_at: int | None
    hashtags: list[str]
    mentions: list[str]

    # Timing
    taken_at: int | None
    duration_seconds: float | None

    # Media flags
    media_type: int | None
    product_type: str | None
    has_audio: bool
    is_dash_eligible: bool
    original_width: int | None
    original_height: int | None

    # URLs
    video_versions: list[VideoVersion]
    video_url_best: str | None
    audio_url: str | None
    audio_codec: str | None
    audio_bandwidth: int | None
    thumbnail_url: str | None
    thumbnail_versions: list[ImageVersion]

    # Engagement
    like_count: int | None
    comment_count: int | None
    view_count: int | None
    like_and_view_counts_disabled: bool

    # Music
    music: MusicInfo | None

    # Permissions / flags
    can_viewer_reshare: bool | None
    is_paid_partnership: bool
    comments_disabled: bool | None
    ig_media_sharing_disabled: bool | None
    sharing_friction_enabled: bool

    # Raw bag for forward-compat — anything not modelled above
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadResult:
    metadata: ReelMetadata
    audio_path: str | None
    thumbnail_path: str | None
    video_path: str | None
    temp_dir: str


class DownloadError(Exception):
    """Errors raised by the downloader.

    `is_retryable` mirrors the contract used by the Celery task in
    workers/tasks.py — transient (network) failures get retried, permanent
    failures (private/deleted/region-blocked) do not.

    `is_private_content` is True when the failure is specifically because the
    content is private or login-walled — the Celery task uses this to delete
    the reel row instead of marking it failed.
    """

    def __init__(
        self,
        message: str,
        *,
        is_retryable: bool = False,
        is_private_content: bool = False,
    ):
        super().__init__(message)
        self.is_retryable = is_retryable
        self.is_private_content = is_private_content


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def download_reel(
    url: str,
    reel_id: str,
    *,
    download_video: bool = False,
) -> DownloadResult:
    """Fetch every available detail about an Instagram reel and download its assets.

    Args:
        url: Public Instagram reel URL (e.g. https://www.instagram.com/reel/XYZ/).
        reel_id: Caller-supplied identifier used to namespace local filenames.
        download_video: If True, also download the highest-quality combined
            video+audio mp4. Off by default — see backlog item.

    Returns:
        DownloadResult with metadata, local audio/thumbnail/video paths, and
        the temp dir the caller should clean up after consuming the files.

    Raises:
        DownloadError: Something went wrong. Inspect ``is_retryable`` to
            decide whether to retry the whole pipeline.
    """
    log = _bound_logger(reel_id)
    log.info("download_reel start | url=%s | download_video=%s", url, download_video)

    # 1) Fetch HTML
    html = _fetch_reel_html(url, log)

    # 2) Pull the embedded GraphQL JSON blob and find the media item
    item = _extract_media_item(html, log)

    # 3) Build the rich metadata dataclass
    metadata = _parse_metadata(item, log)
    log.info(
        "metadata parsed | shortcode=%s | creator=@%s | has_audio=%s | duration=%ss",
        metadata.shortcode,
        metadata.creator_handle,
        metadata.has_audio,
        metadata.duration_seconds,
    )

    # 4) Allocate a temp dir for downloaded assets
    temp_dir = tempfile.mkdtemp(prefix=f"reelmind_{reel_id}_")
    log.info("temp_dir created | path=%s", temp_dir)

    audio_path: str | None = None
    thumbnail_path: str | None = None
    video_path: str | None = None

    try:
        # 5) Download audio (audio-only m4a from DASH)
        if metadata.audio_url:
            audio_path = os.path.join(temp_dir, f"{reel_id}.m4a")
            log.info("downloading audio | dest=%s", audio_path)
            audio_bytes = _download_file(metadata.audio_url, audio_path, log)
            log.info("audio download done | bytes=%s", audio_bytes)
        elif metadata.video_url_best:
            # Fallback: no DASH audio-only stream, but a combined video exists.
            # Download it and strip the audio track with FFmpeg.
            log.warning(
                "no DASH audio URL — trying video+audio fallback | has_audio=%s",
                metadata.has_audio,
            )
            audio_path = _extract_audio_from_video_fallback(
                metadata.video_url_best, reel_id, temp_dir, log
            )
        else:
            log.warning(
                "no audio URL and no video URL — reel reports has_audio=%s "
                "(silent reel or missing DASH manifest)",
                metadata.has_audio,
            )

        # 6) Download thumbnail
        if metadata.thumbnail_url:
            thumbnail_path = os.path.join(temp_dir, f"{reel_id}.jpg")
            log.info("downloading thumbnail | dest=%s", thumbnail_path)
            thumb_bytes = _download_file(metadata.thumbnail_url, thumbnail_path, log)
            log.info("thumbnail download done | bytes=%s", thumb_bytes)
        else:
            log.warning("no thumbnail URL available")

        # 7) Optional video download
        if download_video and metadata.video_url_best:
            video_path = os.path.join(temp_dir, f"{reel_id}.mp4")
            log.info("downloading video | dest=%s", video_path)
            video_bytes = _download_file(metadata.video_url_best, video_path, log)
            log.info("video download done | bytes=%s", video_bytes)

    except Exception:
        # If any download blew up, the caller has no use for the temp dir.
        # Best-effort cleanup so we don't leak it.
        _safe_cleanup(temp_dir)
        raise

    log.info("download_reel done | reel_id=%s", reel_id)
    return DownloadResult(
        metadata=metadata,
        audio_path=audio_path,
        thumbnail_path=thumbnail_path,
        video_path=video_path,
        temp_dir=temp_dir,
    )


# ---------------------------------------------------------------------------
# Stage 1 — fetch HTML
# ---------------------------------------------------------------------------


def _fetch_reel_html(url: str, log: logging.LoggerAdapter) -> str:
    log.info("fetching reel HTML | url=%s", url)
    try:
        resp = cffi_requests.get(url, impersonate="chrome", timeout=30)
    except Exception as exc:
        # exc class name + message gives ops enough to distinguish DNS failure
        # vs TLS handshake failure vs read timeout without re-running.
        log.error(
            "network error fetching reel HTML | exc_type=%s | reason=%s",
            type(exc).__name__,
            exc,
        )
        raise DownloadError(
            f"network error fetching {url}: {type(exc).__name__}: {exc}",
            is_retryable=True,
        ) from exc

    log.info(
        "HTTP response | status=%s | bytes=%s | final_url=%s",
        resp.status_code,
        len(resp.text),
        resp.url,
    )

    if resp.status_code in (401, 403):
        log.error(
            "fetch failed | status=%s | likely_cause=private reel, login-walled, "
            "or IG rate-limited this IP",
            resp.status_code,
        )
        raise DownloadError(
            f"Instagram HTTP {resp.status_code} — private reel / login required / IP rate-limited",
            is_retryable=False,
            is_private_content=True,
        )
    if resp.status_code == 404:
        log.error(
            "fetch failed | status=404 | likely_cause=reel deleted or URL malformed"
        )
        raise DownloadError(
            "Instagram HTTP 404 — reel deleted or wrong URL",
            is_retryable=False,
        )
    if resp.status_code == 429:
        log.warning(
            "fetch failed | status=429 | likely_cause=IG rate-limited this IP, "
            "back off"
        )
        raise DownloadError(
            "Instagram HTTP 429 — rate limited", is_retryable=True
        )
    if resp.status_code >= 500:
        log.warning(
            "fetch failed | status=%s | likely_cause=Instagram server-side issue",
            resp.status_code,
        )
        raise DownloadError(
            f"Instagram HTTP {resp.status_code} — server-side error",
            is_retryable=True,
        )
    if resp.status_code != 200:
        log.warning(
            "fetch failed | status=%s | likely_cause=unexpected response — "
            "treating as transient",
            resp.status_code,
        )
        raise DownloadError(
            f"Instagram HTTP {resp.status_code} — unexpected", is_retryable=True
        )

    # If IG redirected us to /accounts/login, the HTML will be the login page.
    if "/accounts/login" in resp.url or '"LoginAndSignupPage"' in resp.text:
        log.error(
            "fetch failed | status=200 | likely_cause=login-wall redirect "
            "(reel is private or IG demanding session)"
        )
        raise DownloadError(
            "Instagram redirected to login — reel is private or session required",
            is_retryable=False,
            is_private_content=True,
        )

    return resp.text


# ---------------------------------------------------------------------------
# Stage 2 — find the media item inside the embedded JSON
# ---------------------------------------------------------------------------


def _extract_media_item(html: str, log: logging.LoggerAdapter) -> dict[str, Any]:
    """Pull the reel's media dict out of the embedded JSON.

    We don't trust the exact array indices Instagram uses — they shuffle
    them between releases — so we do a recursive search for either of the
    known shortcode-info keys, then take ``.items[0]``.
    """
    log.info("scanning <script type=application/json> blocks for media payload")
    selector = Selector(html)

    blocks = selector.css('script[type="application/json"]::text').getall()
    log.info("found %d JSON script blocks", len(blocks))

    candidates = 0
    for raw in blocks:
        if "video_versions" not in raw and "shortcode" not in raw:
            continue
        candidates += 1
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue

        item = _find_first_media_item(blob)
        if item is not None:
            log.info("media item located in JSON blob #%d", candidates)
            return item

    if _html_signals_private_content(html):
        log.error(
            "JSON locate failed | candidates_scanned=%d | "
            "private_marker=True | reel is from a private account",
            candidates,
        )
        raise DownloadError(
            "Instagram returned a private-account page — no media payload present",
            is_retryable=False,
            is_private_content=True,
        )

    log.error(
        "JSON locate failed | candidates_scanned=%d | likely_cause=IG served "
        "degraded HTML (no JSON blob), changed their page structure, or "
        "returned a logged-out shell",
        candidates,
    )
    raise DownloadError(
        "could not locate reel media payload in HTML — Instagram likely changed "
        "their page structure or returned a degraded response",
        is_retryable=True,
    )


def _find_first_media_item(blob: Any) -> dict[str, Any] | None:
    """Walk the JSON tree and return the first ``items[0]`` we find under
    one of the known shortcode-info keys."""
    for node in _walk_dicts(blob):
        for key in _SHORTCODE_INFO_KEYS:
            inner = node.get(key)
            if isinstance(inner, dict):
                items = inner.get("items")
                if isinstance(items, list) and items:
                    item = items[0]
                    if isinstance(item, dict):
                        return item
    return None


def _walk_dicts(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict node found anywhere under ``node`` (DFS)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_dicts(v)


def _html_signals_private_content(html: str) -> bool:
    """Return True if any <script type=application/json> block contains a dict
    where ``is_private`` is True.

    Instagram serves private-account reel pages as HTTP 200 with user metadata
    JSON (including is_private=True) but no media payload. Scanning for this
    flag lets us distinguish a definitive private-content rejection from a
    transient parse failure.
    """
    selector = Selector(html)
    for raw in selector.css('script[type="application/json"]::text').getall():
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk_dicts(blob):
            if node.get("is_private") is True:
                return True
    return False


# ---------------------------------------------------------------------------
# Stage 3 — parse the rich metadata dataclass from the media item
# ---------------------------------------------------------------------------


def _parse_metadata(item: dict[str, Any], log: logging.LoggerAdapter) -> ReelMetadata:
    log.info("parsing metadata from media item")

    # User
    raw_user = item.get("user") or {}
    user = ReelUser(
        pk=str(raw_user.get("pk") or raw_user.get("id") or ""),
        username=raw_user.get("username") or "",
        full_name=raw_user.get("full_name"),
        profile_pic_url=raw_user.get("profile_pic_url"),
        is_private=bool(raw_user.get("is_private")),
        is_verified=bool(raw_user.get("is_verified")),
        is_embeds_disabled=raw_user.get("is_embeds_disabled"),
    )

    # Caption + hashtags + mentions
    caption_obj = item.get("caption") or {}
    caption_text = caption_obj.get("text") if isinstance(caption_obj, dict) else None
    hashtags = _extract_hashtags(caption_text or "")
    mentions = _extract_mentions(caption_text or "")
    log.info(
        "caption | length=%s | hashtags=%d | mentions=%d",
        len(caption_text) if caption_text else 0,
        len(hashtags),
        len(mentions),
    )

    # Video versions (combined video+audio variants IG ships at the top level)
    video_versions = [
        VideoVersion(
            width=int(v.get("width") or 0),
            height=int(v.get("height") or 0),
            url=v.get("url") or "",
            type=int(v.get("type") or 0),
        )
        for v in (item.get("video_versions") or [])
        if v.get("url")
    ]
    video_url_best = max(
        video_versions,
        key=lambda v: (v.width * v.height),
        default=None,
    )
    video_url_best_str = video_url_best.url if video_url_best else None

    # Thumbnail
    raw_thumbs = (item.get("image_versions2") or {}).get("candidates") or []
    thumbnail_versions = [
        ImageVersion(
            width=int(t.get("width") or 0),
            height=int(t.get("height") or 0),
            url=t.get("url") or "",
        )
        for t in raw_thumbs
        if t.get("url")
    ]
    thumbnail_url = item.get("display_uri") or (
        thumbnail_versions[0].url if thumbnail_versions else None
    )

    # Audio + duration from DASH manifest
    audio_url: str | None = None
    audio_codec: str | None = None
    audio_bandwidth: int | None = None
    duration_seconds: float | None = None
    manifest_xml = item.get("video_dash_manifest")
    if isinstance(manifest_xml, str) and manifest_xml.strip():
        log.info("DASH manifest present | length=%d chars", len(manifest_xml))
        audio_url, audio_codec, audio_bandwidth, duration_seconds = (
            _parse_dash_manifest(manifest_xml, log)
        )
    else:
        log.info("no DASH manifest on media item")

    # Music info — IG splits this into licensed-music vs original-sound branches
    music = _parse_music(item.get("clips_metadata") or {})
    if music:
        log.info(
            "music | type=%s | title=%s | artist=%s",
            music.audio_type,
            music.title,
            music.artist,
        )

    # Sharing friction
    sf = item.get("sharing_friction_info") or {}

    # Build the dataclass
    return ReelMetadata(
        shortcode=item.get("code") or "",
        pk=str(item.get("pk") or ""),
        media_id=item.get("id") or "",
        user=user,
        creator_handle=user.username,
        caption=caption_text,
        caption_created_at=caption_obj.get("created_at") if isinstance(caption_obj, dict) else None,
        hashtags=hashtags,
        mentions=mentions,
        taken_at=item.get("taken_at"),
        duration_seconds=duration_seconds,
        media_type=item.get("media_type"),
        product_type=item.get("product_type"),
        has_audio=bool(item.get("has_audio")),
        is_dash_eligible=bool(item.get("is_dash_eligible")),
        original_width=item.get("original_width"),
        original_height=item.get("original_height"),
        video_versions=video_versions,
        video_url_best=video_url_best_str,
        audio_url=audio_url,
        audio_codec=audio_codec,
        audio_bandwidth=audio_bandwidth,
        thumbnail_url=thumbnail_url,
        thumbnail_versions=thumbnail_versions,
        like_count=item.get("like_count"),
        comment_count=item.get("comment_count"),
        view_count=item.get("view_count"),
        like_and_view_counts_disabled=bool(item.get("like_and_view_counts_disabled")),
        music=music,
        can_viewer_reshare=item.get("can_viewer_reshare"),
        is_paid_partnership=bool(item.get("is_paid_partnership")),
        comments_disabled=item.get("comments_disabled"),
        ig_media_sharing_disabled=item.get("ig_media_sharing_disabled"),
        sharing_friction_enabled=bool(sf.get("should_have_sharing_friction")),
        extra={
            "organic_tracking_token": item.get("organic_tracking_token"),
            "carousel_media_count": item.get("carousel_media_count"),
            "number_of_qualities": item.get("number_of_qualities"),
            "preview_comments": item.get("preview_comments"),
        },
    )


def _extract_hashtags(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _HASHTAG_RE.findall(text):
        lower = match.lower()
        if lower not in seen:
            seen.add(lower)
            out.append(match)
    return out


def _extract_mentions(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _MENTION_RE.findall(text):
        lower = match.lower()
        if lower not in seen:
            seen.add(lower)
            out.append(match)
    return out


def _parse_music(clips_meta: dict[str, Any]) -> MusicInfo | None:
    """Build MusicInfo from either licensed-music or original-sound branches."""
    if not clips_meta:
        return None

    audio_type = clips_meta.get("audio_type")

    # Licensed music branch
    music_info = clips_meta.get("music_info") or {}
    asset = music_info.get("music_asset_info") or {}
    consumption = music_info.get("music_consumption_info") or {}
    if asset:
        return MusicInfo(
            audio_type=audio_type or "licensed_music",
            title=asset.get("title"),
            artist=asset.get("display_artist"),
            audio_cluster_id=asset.get("audio_cluster_id"),
            is_explicit=asset.get("is_explicit"),
            is_trending_in_clips=consumption.get("is_trending_in_clips"),
            should_mute_audio=bool(consumption.get("should_mute_audio")),
            should_mute_audio_reason=consumption.get("should_mute_audio_reason"),
        )

    # Original sound branch (creator's own audio)
    original = clips_meta.get("original_sound_info") or {}
    if original:
        return MusicInfo(
            audio_type=audio_type or "original_sounds",
            title=original.get("original_audio_title"),
            artist=(original.get("ig_artist") or {}).get("username"),
            audio_cluster_id=str(original.get("audio_asset_id") or "") or None,
            is_explicit=None,
            is_trending_in_clips=None,
        )

    return None


# ---------------------------------------------------------------------------
# Stage 3b — DASH manifest parsing (audio URL + duration)
# ---------------------------------------------------------------------------


def _parse_dash_manifest(
    manifest_xml: str, log: logging.LoggerAdapter
) -> tuple[str | None, str | None, int | None, float | None]:
    """Return ``(audio_url, audio_codec, audio_bandwidth, duration_seconds)``.

    Picks the highest-bandwidth audio Representation in the manifest. There
    is usually only one, but this is robust if Instagram ever ships multiple.
    """
    try:
        root = ET.fromstring(manifest_xml)
    except ET.ParseError as exc:
        log.warning("failed to parse DASH manifest XML: %s", exc)
        return None, None, None, None

    # Duration on <MPD mediaPresentationDuration="PT19.435102S">
    duration_seconds: float | None = None
    raw_duration = root.attrib.get("mediaPresentationDuration")
    if raw_duration:
        m = _DURATION_RE.search(raw_duration)
        if m:
            try:
                duration_seconds = float(m.group(1))
            except ValueError:
                pass

    audio_url: str | None = None
    audio_codec: str | None = None
    audio_bandwidth: int | None = None

    # Find every audio AdaptationSet (namespaced and unnamespaced for safety)
    audio_sets = root.findall(
        ".//mpd:AdaptationSet[@contentType='audio']", _MPD_NS
    ) or root.findall(".//AdaptationSet[@contentType='audio']")

    log.info("DASH audio adaptation sets found | count=%d", len(audio_sets))

    best_bandwidth = -1
    for aset in audio_sets:
        reps = aset.findall("mpd:Representation", _MPD_NS) or aset.findall(
            "Representation"
        )
        for rep in reps:
            try:
                bw = int(rep.attrib.get("bandwidth") or 0)
            except ValueError:
                bw = 0
            base_url_el = rep.find("mpd:BaseURL", _MPD_NS) or rep.find("BaseURL")
            if base_url_el is None or not (base_url_el.text or "").strip():
                continue
            if bw > best_bandwidth:
                best_bandwidth = bw
                audio_url = base_url_el.text.strip()
                audio_codec = rep.attrib.get("codecs")
                audio_bandwidth = bw

    if audio_url:
        log.info(
            "audio stream selected | codec=%s | bandwidth=%s | host=%s",
            audio_codec,
            audio_bandwidth,
            urlparse(audio_url).hostname,
        )
    else:
        log.info("no audio Representation with BaseURL in manifest")

    return audio_url, audio_codec, audio_bandwidth, duration_seconds


# ---------------------------------------------------------------------------
# Stage 4 — file downloads
# ---------------------------------------------------------------------------


def _download_file(url: str, dest_path: str, log: logging.LoggerAdapter) -> int:
    """Stream ``url`` to ``dest_path``. Returns bytes written."""
    import urllib.request
    from urllib.error import HTTPError, URLError

    parsed = urlparse(url)
    # CDN URLs don't require full TLS fingerprinting, but setting a standard UA helps.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    )
    try:
        written = 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                written += len(chunk)
        return written
    except HTTPError as exc:
        cause = (
            "CDN server-side issue"
            if exc.code >= 500
            else "asset URL expired or revoked (IG CDN URLs are signed+short-lived)"
        )
        log.error(
            "asset download failed | host=%s | path=%s | status=%s "
            "| likely_cause=%s",
            parsed.hostname,
            parsed.path,
            exc.code,
            cause,
        )
        raise DownloadError(
            f"download HTTP {exc.code} for {parsed.path}: {cause}",
            is_retryable=exc.code >= 500,
        )
    except (URLError, Exception) as exc:
        # Log at WARNING — callers that treat this as non-fatal (e.g. the
        # video-audio fallback) will catch DownloadError and proceed; callers
        # where this is a hard failure will let it propagate and log context there.
        log.warning(
            "asset download failed | host=%s | path=%s | exc_type=%s | reason=%s",
            parsed.hostname,
            parsed.path,
            type(exc).__name__,
            exc,
        )
        raise DownloadError(
            f"network error downloading {parsed.path}: {type(exc).__name__}: {exc}",
            is_retryable=True,
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_audio_from_video_fallback(
    video_url: str,
    reel_id: str,
    temp_dir: str,
    log: logging.LoggerAdapter,
) -> str | None:
    """Download the combined video and extract its audio track.

    Returns the local audio path on success, or None on any failure.
    Never raises — all errors are logged as warnings so the pipeline
    continues without audio rather than crashing.
    """
    from services.ffmpeg_utils import FFmpegError, extract_audio_from_video, is_ffmpeg_available

    if not is_ffmpeg_available():
        log.warning(
            "video-audio fallback skipped — FFmpeg not available; "
            "install imageio-ffmpeg (pip install imageio-ffmpeg) to enable"
        )
        return None

    fallback_video = os.path.join(temp_dir, f"{reel_id}_source.mp4")
    audio_path = os.path.join(temp_dir, f"{reel_id}.m4a")
    try:
        video_bytes = _download_file(video_url, fallback_video, log)
        log.info("fallback video downloaded | bytes=%s", video_bytes)
        extract_audio_from_video(fallback_video, audio_path)
        log.info("audio extracted from video | dest=%s", audio_path)
        return audio_path
    except FFmpegError as exc:
        log.warning(
            "audio extraction failed | ffmpeg_error=%s — proceeding without audio", exc
        )
    except DownloadError as exc:
        log.warning(
            "video download for fallback failed | error=%s — proceeding without audio", exc
        )
    except Exception as exc:
        log.warning(
            "unexpected error in audio fallback | exc_type=%s | reason=%s — "
            "proceeding without audio",
            type(exc).__name__,
            exc,
        )
    finally:
        if os.path.exists(fallback_video):
            try:
                os.remove(fallback_video)
                log.info("removed intermediate fallback video | path=%s", fallback_video)
            except OSError:
                pass
    return None


def _bound_logger(reel_id: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"reel_id": reel_id})


def _safe_cleanup(temp_dir: str) -> None:
    try:
        for name in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, name))
            except OSError:
                pass
        os.rmdir(temp_dir)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# CLI for ad-hoc testing — not used by the worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    if len(sys.argv) < 2:
        print("usage: python -m services.downloader <reel_url> [reel_id]")
        sys.exit(2)

    cli_url = sys.argv[1]
    cli_reel_id = sys.argv[2] if len(sys.argv) > 2 else "cli-test"

    cli_result = download_reel(cli_url, cli_reel_id, download_video=False)

    print("\n--- result ---")
    print(f"shortcode:       {cli_result.metadata.shortcode}")
    print(f"creator:         @{cli_result.metadata.creator_handle} "
          f"(verified={cli_result.metadata.user.is_verified})")
    print(f"caption:         {(cli_result.metadata.caption or '')[:120]!r}")
    print(f"hashtags:        {cli_result.metadata.hashtags}")
    print(f"mentions:        {cli_result.metadata.mentions}")
    print(f"duration:        {cli_result.metadata.duration_seconds}s")
    print(f"has_audio:       {cli_result.metadata.has_audio}")
    print(f"audio_codec:     {cli_result.metadata.audio_codec}")
    print(f"like_count:      {cli_result.metadata.like_count}")
    print(f"comment_count:   {cli_result.metadata.comment_count}")
    if cli_result.metadata.music:
        print(
            f"music:           {cli_result.metadata.music.title} "
            f"by {cli_result.metadata.music.artist} "
            f"({cli_result.metadata.music.audio_type})"
        )
    print(f"audio_path:      {cli_result.audio_path}")
    print(f"thumbnail_path:  {cli_result.thumbnail_path}")
    print(f"video_path:      {cli_result.video_path}")
    print(f"temp_dir:        {cli_result.temp_dir}")
