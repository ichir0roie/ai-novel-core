from data_access_logic.material import Material
from db.schema import ConfirmStatus


class MemeRecord(Material):
    id: int
    category: str | None = None
    confirmed: ConfirmStatus
    text: str
