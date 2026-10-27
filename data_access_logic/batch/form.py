from typing import Any

from data_access_logic.material import Form


class BatchRequest(Form):
    # 呼ぶ入口の id(「領域.ファイル.クラス」。`batch.run_batch.BATCH_ENTRANCES` のどれか)
    entrance: str
    # その入口を一件だけ呼ぶときと同じ引数
    args: dict[str, Any] = {}
