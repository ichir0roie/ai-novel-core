#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.flows import commit
from data_access_logic.story import steps
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord


# 確定のあと(`run()` / `show()`)は、作品の筋書きから出来事の種を AI で抜き出す(`flows/commit.py`)
class CommitStory(CommitEntrypoint):
    def __init__(self, story: StoryCreateForm):
        self.story = story

    def execute(self, s: Session) -> StoryRecord:
        return steps.commit_story(s, self.story)

    def result(self) -> StoryRecord:
        return commit.commit_story(self.story)
