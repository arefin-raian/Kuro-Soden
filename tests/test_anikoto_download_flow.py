import pytest
from nekofetch.sources.miruro import MiruroSource

from nekofetch.domain.enums import AudioType
from nekofetch.services.download_service import DownloadWorker
from nekofetch.sources.anikoto import AnikotoSource
from nekofetch.sources.base import Episode, VideoVariant


@pytest.mark.asyncio
async def test_anikoto_variants_ignore_hardsub_candidates():
    src = AnikotoSource()

    async def collect_mapper(_mal, _slug, _timestamp, add):
        add("hsub", "https://hard.example/master.m3u8", "https://hard.example/")
        add("sub", "https://soft.example/master.m3u8", "https://soft.example/")
        add("dub", "https://dub.example/master.m3u8", "https://dub.example/")

    async def collect_server_list(_ids, add):
        add("H-Sub", "https://hard-2.example/master.m3u8", "https://hard-2.example/")

    async def qualities(_cands):
        return ["480"]

    src._collect_mapper = collect_mapper
    src._collect_server_list = collect_server_list
    src._available_qualities = qualities

    variants = await src.get_variants("video/ids/mal/timestamp/slug")

    assert [(v.audio, v.resolution) for v in variants] == [
        (AudioType.SUBBED, "480p"),
        (AudioType.DUBBED, "480p"),
    ]
    for variant in variants:
        assert "hard" not in variant.source_ref

    plan = await src.dual_audio_plan("video/ids/mal/timestamp/slug", resolution="1080p")
    assert plan["feasible"] is False


@pytest.mark.asyncio
async def test_best_variant_honors_requested_resolution():
    worker = object.__new__(DownloadWorker)

    class Source:
        name = "fake"

        async def get_variants(self, _ref):
            return [
                VideoVariant("sub-720", "720p", AudioType.SUBBED),
                VideoVariant("sub-480", "480p", AudioType.SUBBED),
                VideoVariant("dub-720", "720p", AudioType.DUBBED),
            ]

    source = Source()
    chain = [(source, [Episode("ep-ref", season=1, number=1)])]

    picked = await worker._best_variant(chain, 1, AudioType.SUBBED, "480p")
    assert picked == (source, VideoVariant("sub-480", "480p", AudioType.SUBBED), "ep-ref")

    missing = await worker._best_variant(chain, 1, AudioType.DUBBED, "480p")
    assert missing is None


@pytest.mark.asyncio
async def test_miruro_prefers_soft_sub_before_hardsub():
    src = MiruroSource(base_url="http://localhost:8000")
    hard = VideoVariant('{"hard_sub": true}', "720p", AudioType.SUBBED)
    soft = VideoVariant(
        '{"hard_sub": false, "subtitles": [["English", "https://subs.example/en.vtt"]]}',
        "720p",
        AudioType.SUBBED,
        subtitles=["English"],
    )
    dub = VideoVariant('{"hard_sub": false}', "720p", AudioType.DUBBED)

    async def refs(_episode_ref):
        return ["watch/provider/1/sub/example"]

    async def variants(_watch_ref):
        return [hard, dub, soft]

    src._watch_refs_for_episode = refs
    src._variants_for_watch_ref = variants

    got = await src.get_variants("miruro:1:1")
    subbed = [v for v in got if v.audio == AudioType.SUBBED]

    assert subbed == [soft, hard]


@pytest.mark.asyncio
async def test_miruro_dual_plan_rejects_hardsub_sub_track():
    src = MiruroSource(base_url="http://localhost:8000")
    hard = VideoVariant(
        '{"hard_sub": true, "stream": "https://video.example/sub.m3u8", "headers": {}}',
        "720p",
        AudioType.SUBBED,
    )
    dub = VideoVariant(
        '{"hard_sub": false, "stream": "https://video.example/dub.m3u8", "headers": {}}',
        "720p",
        AudioType.DUBBED,
    )

    async def variants(_episode_ref):
        return [hard, dub]

    src.get_variants = variants

    plan = await src.dual_audio_plan("miruro:1:1", resolution="720p")

    assert plan["feasible"] is False
    assert plan["mergeable"] is False
    assert plan["reason"] == "missing soft sub or dub"

    no_track_sub = VideoVariant(
        '{"hard_sub": false, "stream": "https://video.example/sub.m3u8", "subtitles": []}',
        "720p",
        AudioType.SUBBED,
    )

    async def no_track_variants(_episode_ref):
        return [no_track_sub, dub]

    src.get_variants = no_track_variants
    no_track_plan = await src.dual_audio_plan("miruro:1:1", resolution="720p")

    assert no_track_plan["feasible"] is False


@pytest.mark.asyncio
async def test_miruro_dual_plan_allows_matching_soft_sub_and_dub(monkeypatch):
    import nekofetch.sources._dualaudio as dualaudio

    src = MiruroSource(base_url="http://localhost:8000")
    soft = VideoVariant(
        (
            '{"hard_sub": false, "stream": "https://video.example/sub.m3u8", '
            '"headers": {}, "subtitles": [["English", "https://subs.example/en.vtt"]]}'
        ),
        "720p",
        AudioType.SUBBED,
        subtitles=["English"],
    )
    dub = VideoVariant(
        '{"hard_sub": false, "stream": "https://video.example/dub.m3u8", "headers": {}}',
        "720p",
        AudioType.DUBBED,
    )

    async def variants(_episode_ref):
        return [soft, dub]

    async def duration(_http, _url, _headers):
        return 1410.0

    src.get_variants = variants
    monkeypatch.setattr(dualaudio, "playlist_duration", duration)

    plan = await src.dual_audio_plan("miruro:1:1", resolution="720p")

    assert plan["feasible"] is True
    assert plan["mergeable"] is True
    assert plan["sub_variant"] == soft
    assert plan["dub_variant"] == dub


def test_miruro_subtitle_pairs_drop_thumbnail_tracks():
    """hi-anime/zoro feeds put a preview-sprite VTT in the subtitles array. It must
    NOT be embedded as a caption, and must not make a raw stream look soft-subbed."""
    from nekofetch.sources.miruro import _subtitle_pairs

    tracks = [
        {"file": "https://cdn.example/thumbs.vtt", "kind": "thumbnails"},
        {"file": "https://cdn.example/sprite.vtt", "label": "Thumbnails"},
        {"file": "https://cdn.example/en.vtt", "label": "English", "kind": "captions"},
    ]
    pairs = _subtitle_pairs(tracks)
    assert pairs == [("English", "https://cdn.example/en.vtt")]


@pytest.mark.asyncio
async def test_miruro_variants_fall_back_to_sources_endpoint():
    """When GET /{watch_ref} returns no streams, the source must retry the
    documented /sources fallback before giving up on the episode."""
    src = MiruroSource(base_url="http://localhost:8000")
    calls: list[tuple[str, dict | None]] = []

    async def fake_get_json(path, *, params=None):
        calls.append((path, params))
        if path == "/sources":
            return {
                "streams": [{"url": "https://cdn.example/master.m3u8", "quality": "1080p"}],
                "subtitles": [{"file": "https://cdn.example/en.vtt", "label": "English"}],
            }
        return {}  # primary watch endpoint yields nothing

    async def fake_master(_http, _url, _headers):
        return [1080]

    import nekofetch.sources.miruro as miruro_mod
    src._get_json = fake_get_json
    orig = miruro_mod.list_master_qualities
    miruro_mod.list_master_qualities = fake_master
    try:
        variants = await src._variants_for_watch_ref("watch/kiwi/178005/sub/animepahe-1")
    finally:
        miruro_mod.list_master_qualities = orig

    assert any(path == "/sources" for path, _ in calls), "fallback /sources was not called"
    assert variants and variants[0].audio == AudioType.SUBBED
    assert variants[0].resolution == "1080p"
