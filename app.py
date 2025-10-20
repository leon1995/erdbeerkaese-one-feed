"""Application to host the merge feed."""

from datetime import UTC, datetime

import cachetools
import feedparser
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import PlainTextResponse
from feedgen.feed import FeedEntry, FeedGenerator

__ACAST_URL = 'https://feeds.acast.com/public/shows/erdbeerkaesepodcast'
__PATREON_URL = (
    'https://www.patreon.com/rss/erdbeerkaese?auth={patreon_auth_token}&show=875519'
)
__CACHE_TTL__ = 60  # acast default. may be increased if server cant handle it
__HTTP_ERROR__ = 400


def _set_feed_data(
    merged_feed: FeedGenerator, acast_data: dict, patreon_data: dict
) -> None:
    merged_feed.title(acast_data['title'])
    merged_feed.description(acast_data['summary'])

    for link in acast_data.get('links', []):
        merged_feed.link(
            rel=link.get('rel'),
            href=link.get('href'),
            type=link.get('type'),
            length=link.get('length'),
            title=link.get('title', 'Acast Feed'),
        )
    patreon_link = next(
        (link for link in patreon_data['links'] if link.get('rel') == 'self'),
        None
    )
    if patreon_link:
        merged_feed.link(
            rel='related',
            href=patreon_link['href'],
            type='application/rss+xml',
            title='Patreon Feed',
        )

    merged_feed.language(acast_data['language'])
    merged_feed.rights(acast_data['rights'])
    merged_feed.ttl(acast_data.get('ttl', __CACHE_TTL__))
    merged_feed.generator('Acast and Patreon')

    author_detail = acast_data['author_detail']
    merged_feed.author(
        name=author_detail.get('name'), email=author_detail.get('email'), replace=True
    )
    merged_feed.managingEditor(author_detail.get('email'))

    # Image information
    image = acast_data['image']
    merged_feed.image(
        url=image.get('href'), title=image.get('title'), link=image.get('link')
    )

    for tag in acast_data.get('tags', []):
        merged_feed.category(
            term=tag.get('term'), scheme=tag.get('scheme'), label=tag.get('label')
        )

    # not available in patreon feed
    merged_feed.podcast.itunes_explicit(acast_data['itunes_explicit'])
    merged_feed.podcast.itunes_type(acast_data['itunes_type'])

    merged_feed.podcast.itunes_author(author_detail.get('name'))
    merged_feed.podcast.itunes_image(image.get('href'))
    merged_feed.podcast.itunes_subtitle(patreon_data['subtitle'])
    merged_feed.podcast.itunes_summary(acast_data['summary'])
    merged_feed.podcast.itunes_owner(
        name=author_detail.get('name'), email=author_detail.get('email')
    )

    merged_feed.lastBuildDate(datetime.now(UTC))


def _set_feed_entry_data(fe: FeedEntry, entry: dict, number: int) -> None:
    fe.title(entry['title'])

    for link in entry.get('links'):
        fe.link(
            rel=link.get('rel'),
            href=link.get('href'),
            type=link.get('type'),
            length=link.get('length'),
        )

    summary_detail = entry['summary_detail']
    fe.summary(summary_detail['value'], type=summary_detail['type'])

    fe.guid(entry['id'], permalink=entry['guidislink'])
    fe.published(entry['published'])

    # not available in patreon feed
    fe.podcast.itunes_season(entry.get('itunes_season', 1))
    fe.podcast.itunes_episode(number)
    fe.podcast.itunes_explicit(entry.get('itunes_explicit'))
    fe.podcast.itunes_duration(entry.get('itunes_duration'))
    fe.podcast.itunes_episode_type(entry.get('itunes_episodetype', 'full'))
    fe.podcast.itunes_title(entry.get('itunes_title'))


@cachetools.cached(cache=cachetools.TTLCache(maxsize=1024, ttl=__CACHE_TTL__))
def generate_merged_feed(patreon_auth_token: str) -> FeedGenerator:
    """Generate the merged RSS feed by fetching both feeds dynamically.

    Args:
        patreon_auth_token: Required Patreon auth token for personalized Patreon feed

    """
    acast_feed = feedparser.parse(__ACAST_URL)
    if acast_feed.status >= __HTTP_ERROR__:
        raise HTTPException(
            status_code=acast_feed.status, detail='Error fetching Acast feed'
        )
    patreon_feed = feedparser.parse(
        __PATREON_URL.format(patreon_auth_token=patreon_auth_token)
    )
    if patreon_feed.status >= __HTTP_ERROR__:
        raise HTTPException(
            status_code=patreon_feed.status,
            detail='Error fetching Patreon feed. Auth token correct?',
        )

    # Create merged feed using public feed as base
    merged_feed = FeedGenerator()
    merged_feed.load_extension('podcast')

    _set_feed_data(merged_feed, acast_feed['feed'], patreon_feed['feed'])

    raw_entries = acast_feed.get('entries', []) + patreon_feed.get('entries', [])
    raw_entries.sort(key=lambda x: x['published_parsed'])

    for i, entry in enumerate(raw_entries, start=1):
        fe = merged_feed.add_entry(order='append')
        _set_feed_entry_data(fe, entry, i)

    return merged_feed

app = FastAPI(
    title='Erdbeerkäse Feed Merger',
    description='Merges Acast and Patreon feeds into a single RSS feed',
)


@app.get('/rss', response_class=PlainTextResponse)
async def rss(auth: str) -> Response:
    """Get the merged RSS feed with Patreon auth token.

    Args:
        auth: Patreon auth token for personalized Patreon feed

    """
    try:
        feed_content = generate_merged_feed(auth).rss_str()
        return Response(
            content=feed_content,
            media_type='application/rss+xml',
            headers={
                'Cache-Control': f'public, max-age={__CACHE_TTL__}',
                'Content-Type': 'application/rss+xml; charset=utf-8',
            },
        )
    except HTTPException:
        raise  # do not reraise HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error serving feed: {e!s}') from e


@app.get('/atom', response_class=PlainTextResponse)
async def atom(auth: str) -> Response:
    """Get the merged atom feed with Patreon auth token.

    Args:
        auth: Patreon auth token for personalized Patreon feed

    """
    try:
        feed_content = generate_merged_feed(auth).atom_str()
        return Response(
            content=feed_content,
            media_type='application/atom+xml',
            headers={
                'Cache-Control': f'public, max-age={__CACHE_TTL__}',
                'Content-Type': 'application/atom+xml; charset=utf-8',
            },
        )
    except HTTPException:
        raise  # do not reraise HTTPException
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error serving feed: {e!s}') from e
