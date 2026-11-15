"""Metadata link fields must apply the same URI scheme whitelist as the
HTML content layer.

Unsafe schemes such as ``javascript:`` and ``vbscript:`` must not pass
through the metadata "promotion" paths (entry/feed link, enclosure,
permalink, icon, generator, source, extension namespaces, JSON Feed).
Relative-URI completion must keep working, and opaque identifiers
(``tag:``/``urn:`` ids) must be preserved.

Each XML case is parsed twice: with the strict SAX parser and with the
loose SGML parser (via the ``use_loose_parser`` fixture), so every exit
is verified under both parser implementations.
"""

from __future__ import annotations

import io

import pytest

import feedparser
import feedparser.urls

BASE = "http://example.com/feed/"

UNSAFE = "javascript:alert(1)"
UNSAFE_2 = "vbscript:msgbox(1)"


# ---------------------------------------------------------------------------
# make_safe_absolute_uri() no-base branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri, expected",
    (
        (UNSAFE, ""),
        (UNSAFE_2, ""),
        ("http://ok.test/", "http://ok.test/"),
        ("mailto:a@b.com", "mailto:a@b.com"),
        ("/rel/path", "/rel/path"),
        ("relative/path", "relative/path"),
        ("#anchor", "#anchor"),
        ("//cdn.test/a", "//cdn.test/a"),
    ),
)
def test_make_safe_absolute_uri_no_base(uri, expected):
    assert feedparser.urls.make_safe_absolute_uri("", uri) == expected


def test_make_safe_absolute_uri_no_base_whitelist_disabled(monkeypatch):
    monkeypatch.setattr(feedparser.urls, "ACCEPTABLE_URI_SCHEMES", ())
    assert feedparser.urls.make_safe_absolute_uri("", UNSAFE) == UNSAFE


# ---------------------------------------------------------------------------
# RSS metadata exits
# ---------------------------------------------------------------------------


RSS_TEMPLATE = """<?xml version="1.0"?>
<rss version="2.0"{base} xmlns:wfw="http://wellformedweb.org/CommentAPI/">
<channel>
  <title>feed</title>
  <link>http://example.com/</link>
  <docs>{docs}</docs>
  <item>
    <title>entry</title>
    <link>{link}</link>
    <comments>{comments}</comments>
    <wfw:commentRss>{wfw}</wfw:commentRss>
    <enclosure url="{enclosure}" length="10" type="audio/mpeg"/>
    <source url="{source}">the source</source>
  </item>
</channel>
</rss>"""


def _rss(with_base):
    base_attr = f' xml:base="{BASE}"' if with_base else ""
    return RSS_TEMPLATE.format(
        base=base_attr,
        docs=UNSAFE,
        link=UNSAFE,
        comments=UNSAFE_2,
        wfw=UNSAFE,
        enclosure=UNSAFE,
        source=UNSAFE,
    )


@pytest.mark.parametrize("with_base", (False, True))
def test_rss_unsafe_schemes_stripped(with_base, request):
    if with_base is False:
        request.getfixturevalue("use_loose_parser")
    result = feedparser.parse(_rss(with_base))
    entry = result.entries[0]

    assert result.feed["docs"] == ""
    assert entry["link"] == ""
    assert entry["comments"] == ""
    assert entry["wfw_commentrss"] == ""
    assert entry["source"]["href"] == ""
    # enclosure is derived from links (rel=enclosure)
    enclosure_links = [link for link in entry["links"] if link["rel"] == "enclosure"]
    assert enclosure_links and all(
        link["href"] == "" for link in enclosure_links
    )


def test_rss_relative_completion_with_base():
    xml = RSS_TEMPLATE.format(
        base=f' xml:base="{BASE}"',
        docs="docs.html",
        link="post/1",
        comments="#c",
        wfw="comments.xml",
        enclosure="files/a.mp3",
        source="src.xml",
    )
    result = feedparser.parse(xml)
    entry = result.entries[0]
    assert result.feed["docs"] == "http://example.com/feed/docs.html"
    assert entry["link"] == "http://example.com/feed/post/1"
    assert entry["comments"] == "http://example.com/feed/#c"
    assert entry["wfw_commentrss"] == "http://example.com/feed/comments.xml"
    assert entry["source"]["href"] == "http://example.com/feed/src.xml"
    enclosure = [link for link in entry["links"] if link["rel"] == "enclosure"][0]
    assert enclosure["href"] == "http://example.com/feed/files/a.mp3"


def test_rss_relative_preserved_without_base():
    xml = RSS_TEMPLATE.format(
        base="",
        docs="docs.html",
        link="post/1",
        comments="#c",
        wfw="comments.xml",
        enclosure="//cdn/a.mp3",
        source="src.xml",
    )
    result = feedparser.parse(xml)
    entry = result.entries[0]
    assert result.feed["docs"] == "docs.html"
    assert entry["link"] == "post/1"
    assert entry["comments"] == "#c"
    assert entry["wfw_commentrss"] == "comments.xml"
    enclosure = [link for link in entry["links"] if link["rel"] == "enclosure"][0]
    assert enclosure["href"] == "//cdn/a.mp3"


# ---------------------------------------------------------------------------
# Atom metadata exits
# ---------------------------------------------------------------------------


ATOM_TEMPLATE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"{base}>
  <icon>{icon}</icon>
  <logo>{logo}</logo>
  <generator href="{generator}">gen</generator>
  <entry>
    <title>entry</title>
    <link rel="alternate" href="{alt}"/>
    <link rel="enclosure" href="{enclosure}" type="video/mp4"/>
    <id>{entry_id}</id>
  </entry>
</feed>"""


@pytest.mark.parametrize("with_base", (False, True))
def test_atom_unsafe_schemes_stripped(with_base, request):
    if with_base is False:
        request.getfixturevalue("use_loose_parser")
    base_attr = f' xml:base="{BASE}"' if with_base else ""
    xml = ATOM_TEMPLATE.format(
        base=base_attr,
        icon=UNSAFE,
        logo=UNSAFE_2,
        generator=UNSAFE,
        alt=UNSAFE,
        enclosure=UNSAFE,
        entry_id="tag:example.com,2026:1",
    )
    result = feedparser.parse(xml)
    entry = result.entries[0]

    assert result.feed["icon"] == ""
    assert result.feed["logo"] == ""
    assert result.feed["generator_detail"]["href"] == ""
    assert entry["id"] == "tag:example.com,2026:1"
    for link in entry["links"]:
        assert link["href"] == ""


def test_atom_legal_and_relative_unchanged():
    xml = ATOM_TEMPLATE.format(
        base=f' xml:base="{BASE}"',
        icon="icon.png",
        logo="/logo.png",
        generator="gen",
        alt="post/1",
        enclosure="https://cdn.test/v.mp4",
        entry_id="/relative/id",
    )
    result = feedparser.parse(xml)
    entry = result.entries[0]
    assert result.feed["icon"] == "http://example.com/feed/icon.png"
    assert result.feed["logo"] == "http://example.com/logo.png"
    assert entry["id"] == "http://example.com/relative/id"
    enclosure = [link for link in entry["links"] if link["rel"] == "enclosure"][0]
    assert enclosure["href"] == "https://cdn.test/v.mp4"


# ---------------------------------------------------------------------------
# Opaque identifiers (guid / id) must be preserved regardless of scheme
# ---------------------------------------------------------------------------


def test_guid_identifiers_preserved_without_base():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
  <item><title>a</title><link>http://e.com/a</link>
    <guid isPermaLink="false">urn:uuid:1234</guid></item>
  <item><title>b</title><link>http://e.com/b</link>
    <guid>tag:example.com,2006:/blog/</guid></item>
</channel></rss>"""
    result = feedparser.parse(xml)
    assert result.entries[0]["id"] == "urn:uuid:1234"
    assert result.entries[0]["guidislink"] is False
    assert result.entries[1]["id"] == "tag:example.com,2006:/blog/"


# ---------------------------------------------------------------------------
# Extension namespaces
# ---------------------------------------------------------------------------


def test_itunes_image_filtered():
    xml = f"""<?xml version="1.0"?>
<rss version="2.0" xml:base="{BASE}"
 xmlns:itunes="http://www.itunes.com/DTDs/Podcast-1.0.dtd">
<channel><title>t</title><link>http://example.com/</link>
  <itunes:image href="{UNSAFE}"/>
</channel></rss>"""
    result = feedparser.parse(xml)
    assert result.feed["image"]["href"] == ""


def test_media_rss_urls_filtered():
    xml = f"""<?xml version="1.0"?>
<rss version="2.0" xml:base="{BASE}"
 xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>t</title><link>http://example.com/</link>
<item><title>x</title><link>http://example.com/x</link>
  <media:content url="{UNSAFE}" type="video/mp4"/>
  <media:thumbnail url="{UNSAFE_2}"/>
  <media:player url="{UNSAFE}"/>
</item></channel></rss>"""
    result = feedparser.parse(xml)
    entry = result.entries[0]
    assert entry["media_content"][0]["url"] == ""
    assert entry["media_thumbnail"][0]["url"] == ""
    assert entry["media_player"]["url"] == ""


def test_creative_commons_license_filtered():
    xml = f"""<?xml version="1.0"?>
<rss version="2.0" xml:base="{BASE}"
 xmlns:cc="http://backend.userland.com/creativeCommonsRssModule">
<channel><title>t</title><link>http://example.com/</link>
<item><title>x</title><link>http://example.com/x</link>
  <cc:license>{UNSAFE}</cc:license>
</item></channel></rss>"""
    result = feedparser.parse(xml)
    license_links = [
        link for link in result.entries[0]["links"] if link["rel"] == "license"
    ]
    assert license_links and all(
        link["href"] == "" for link in license_links
    )


def test_generic_unknown_tag_attributes_filtered():
    # thr: has no dedicated namespace module, so it uses the generic
    # unknown-tag fallback; its href must still be whitelisted.
    xml = f"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="{BASE}"
 xmlns:thr="http://purl.org/syndication/thread/1.0">
<entry><title>x</title><link href="http://example.com/x"/>
  <thr:in-reply-to href="{UNSAFE}" ref="r" type="text/html"/>
</entry></feed>"""
    result = feedparser.parse(xml)
    assert result.entries[0]["thr_in-reply-to"]["href"] == ""


def test_psc_chapter_href_filtered():
    xml = f"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:base="{BASE}"
 xmlns:psc="http://podlove.org/simple-chapters">
<entry><title>x</title><link href="http://example.com/x"/>
  <psc:chapters version="1.1">
    <psc:chapter start="00:00:00" title="c" href="{UNSAFE}"/>
  </psc:chapters>
</entry></feed>"""
    result = feedparser.parse(xml)
    chapter = result.entries[0]["psc_chapters"]["chapters"][0]
    assert chapter["href"] == ""


# ---------------------------------------------------------------------------
# JSON Feed
# ---------------------------------------------------------------------------


JSON_DOC = """{{
  "version": "https://jsonfeed.org/version/1",
  "title": "t",
  "icon": "{icon}",
  "home_page_url": "{home}",
  "items": [{{
    "id": "1",
    "title": "a",
    "url": "{url}",
    "external_url": "{external}",
    "author": {{"name": "me", "url": "{author_url}"}},
    "attachments": [
      {{"url": "{attachment}", "mime_type": "video/mp4"}}
    ]
  }}]
}}"""


def _parse_json(with_base):
    headers = {"content-type": "application/feed+json"}
    if with_base:
        headers["content-location"] = "http://j.test/feed.json"
    doc = JSON_DOC.format(
        icon=UNSAFE,
        home="/home" if with_base else UNSAFE,
        author_url=UNSAFE,
        url="/post/1" if with_base else UNSAFE,
        external=UNSAFE,
        attachment=UNSAFE,
    )
    return feedparser.parse(io.BytesIO(doc.encode()), response_headers=headers)


def test_json_unsafe_schemes_stripped_with_base():
    result = _parse_json(with_base=True)
    entry = result.entries[0]
    assert result.feed["image"] == ""
    assert result.feed["link"] == "http://j.test/home"
    assert entry["link"] == "http://j.test/post/1"
    assert entry["source"] == ""
    # the unsafe author url is stripped to an empty href
    author_detail = dict.get(entry, "author_detail")
    assert author_detail is not None
    assert author_detail.get("href") == ""
    # enclosures is stored directly by the JSON parser
    enclosures = dict.__getitem__(entry, "enclosures")
    assert enclosures[0]["href"] == ""


def test_json_unsafe_schemes_stripped_without_base():
    result = _parse_json(with_base=False)
    entry = result.entries[0]
    assert result.feed["image"] == ""
    assert result.feed["link"] == ""
    assert entry["link"] == ""
    enclosures = dict.__getitem__(entry, "enclosures")
    assert enclosures[0]["href"] == ""
