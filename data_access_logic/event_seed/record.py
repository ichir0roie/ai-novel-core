from data_access_logic.material import Material


class EventSeedRecord(Material):
    id: int
    origin: str = "user"
    text: str
    consolidated: bool
