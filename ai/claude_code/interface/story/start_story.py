#!/usr/bin/env python3
from __future__ import annotations

from pydantic import BaseModel, SerializeAsAny

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from data_access_logic.episode.record import EpisodeHead
from data_access_logic.material import Timestamp
from data_access_logic.query import common_query

_STOPPED_MESSAGE = ("未同期の話が残っている。モード 3(世界観更新)を先に通して、"
                    "SetEpisodeSynced で同期フラグを立ててから書き始める")


class StoryStart(BaseModel):
    """未同期の話が残っていれば `stopped` を立て、材料(`time` から下)は読まない。"""

    story: _rows.StoryDigest
    unsynced: list[_rows.UnsyncedEpisode]
    stopped: bool
    message: str | None = None
    time: Timestamp | None = None
    episodes: list[SerializeAsAny[EpisodeHead]] = []
    # 作品に立つ場所が無ければ読まない
    cast: _rows.Cast | None = None
    brief: _rows.Brief | None = None


class StartStory(StoryQuery):
    def __init__(self, story_id: int, time=None, episodes: int = 10, count: int = 5,
                 reach: int = 60, levels: int = 1, skip_sync: bool = False):
        self.story_id = story_id
        self.time = time
        self.episodes = episodes
        self.count = count
        self.reach = reach
        self.levels = levels
        self.skip_sync = skip_sync

    def execute(self, session) -> StoryStart:
        story = common_query.get_story(session, self.story_id)
        unsynced = _rows.unsynced_episodes(session, self.story_id)
        if unsynced and not self.skip_sync:
            return StoryStart(story=_rows.story_digest(session, story), unsynced=unsynced, stopped=True,
                              message=_STOPPED_MESSAGE)

        _, until = common_query.resolve_time(session, self.time, story)
        start = StoryStart(story=_rows.story_digest(session, story), unsynced=unsynced, stopped=False, time=until,
                           episodes=_rows.episodes(session, self.story_id, count=self.episodes))
        if story.place_id is not None:
            start.cast = _rows.cast(session, self.story_id, until, count=self.count, levels=self.levels)
            start.brief = _rows.brief(session, story.place_id, until, reach=self.reach)
        return start
