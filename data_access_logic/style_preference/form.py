import enum

from pydantic import Field

from data_access_logic.material import Form


class StyleTarget(enum.StrEnum):
    """shared はどの対象にも効く。ほかは `ai/instructions/style.py` の STYLE_BASES のキー。"""

    SHARED = "shared"
    EPISODE = "episode"
    STORY = "story"
    EVENT = "event"
    IDEA = "idea"


class StylePreferenceCreateForm(Form):
    target: StyleTarget
    text: str = Field(min_length=1)


class StylePreferenceUpdateForm(Form):
    id: int
    target: StyleTarget | None = None
    text: str | None = Field(default=None, min_length=1)
