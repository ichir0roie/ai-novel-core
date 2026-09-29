from pydantic import field_validator

from data_access_logic.material import Form
from db.schema import ConfirmStatus, MemeCategory


class MemeCreateForm(Form):
    text: str
    # 空なら次の抽出で AI が振る
    category: MemeCategory | None = None
    # ユーザが書いたミームなので、抜き出し(未確認)と違って承認で入れる
    confirmed: ConfirmStatus = ConfirmStatus.APPROVED

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text は必須")
        return value


class MemeUpdateForm(Form):
    id: int
    text: str | None = None
    category: MemeCategory | None = None
    confirmed: ConfirmStatus | None = None
