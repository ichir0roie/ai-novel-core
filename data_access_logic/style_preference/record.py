from data_access_logic.material import Material
from data_access_logic.style_preference.form import StyleTarget


class StylePreferenceRecord(Material):
    id: int
    target: StyleTarget
    text: str
