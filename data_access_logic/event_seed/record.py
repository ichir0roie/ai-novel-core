from data_access_logic.material import Material


class EventSeedRecord(Material):
    id: int
    text: str
    consolidated: bool
