from pydantic import Field

from data_access_logic.material import Form


class OracleCreateForm(Form):
    text: str = Field(min_length=1)
    title: str | None = None


class OracleUpdateForm(Form):
    id: int
    text: str | None = Field(default=None, min_length=1)
    title: str | None = None
