from data_access_logic.material import Material


class StylePreferenceRecord(Material):
    id: int
    text: str
    scope: str


class WritingStyleRecord(Material):
    text: str
