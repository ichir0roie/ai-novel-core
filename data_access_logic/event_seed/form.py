from data_access_logic.material import Form


class EventSeedUpdateForm(Form):
    id: int
    text: str | None = None
    consolidated: bool | None = None
