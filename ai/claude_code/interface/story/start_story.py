#!/usr/bin/env python3
from __future__ import annotations

from ai.claude_code.interface.story import _rows
from ai.claude_code.interface.story._base import StoryQuery
from data_access_logic.query import common_query


class StartStory(StoryQuery):
    def __init__(self, story_id: int, time=None, plots: int = 10, count: int = 5,
                 reach: int = 60, levels: int = 1, skip_sync: bool = False):
        self.story_id = int(story_id)
        self.time = time
        self.plots = plots
        self.count = count
        self.reach = reach
        self.levels = levels
        self.skip_sync = skip_sync

    def execute(self, session) -> dict:
        story = common_query.get_story(session, self.story_id)
        unsynced = _rows.unsynced_plots(session, self.story_id)
        result = {
            "story": _rows.story_digest(session, story),
            "unsynced": unsynced,
            "stopped": bool(unsynced) and not self.skip_sync,
        }
        if result["stopped"]:
            result["message"] = (
                "未同期の話が残っている。モード 3(世界観更新)を先に通して、"
                "set_plot_synced で同期フラグを立ててから書き始める")
            return result

        _, until = common_query.resolve_time(session, self.time, story)
        result["time"] = str(until)
        result["plots"] = _rows.plots(session, self.story_id, count=int(self.plots))
        if story.place_id is not None:
            result["cast"] = _rows.cast(session, self.story_id, until, count=int(self.count),
                                        levels=int(self.levels))
            result["brief"] = _rows.brief(session, story.place_id, until,
                                          reach=int(self.reach))
        return result
