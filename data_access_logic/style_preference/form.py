from pydantic import Field

from data_access_logic.material import Form


class StylePreferenceCreateForm(Form):
    text: str = Field(min_length=1)


class StylePreferenceUpdateForm(Form):
    id: int
    text: str | None = Field(default=None, min_length=1)
