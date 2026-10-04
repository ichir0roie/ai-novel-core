#!/usr/bin/env python3
from __future__ import annotations

from sqlalchemy.orm import Session

from data_access_logic.entrypoint import CommitEntrypoint
from data_access_logic.story import steps
from data_access_logic.story.form import StoryCreateForm
from data_access_logic.story.record import StoryRecord


class CommitStory(CommitEntrypoint):
    def __init__(self, story: StoryCreateForm):
        self.story = story

    def execute(self, s: Session) -> StoryRecord:
        return steps.commit_story(s, self.story)
