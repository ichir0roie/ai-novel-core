# データ編集 GUI の API(gui/api、FastAPI)を AWS Lambda で動かすコンテナ。
# Lambda Web Adapter(拡張として /opt/extensions に置く)が Lambda のイベントを HTTP に直して uvicorn へ流すので、
# アプリは普段どおり uvicorn で起こすだけでよい。ビルドはリポジトリのルートを文脈にする:
# https://github.com/aws/aws-lambda-web-adapter
#   docker build --platform linux/amd64 --provenance=false -f infra/lambda/Dockerfile -t novel-api .
#
# 使い方・環境変数は `.docs/aws-deploy.md`。
FROM public.ecr.aws/docker/library/python:3.14-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# db は DEM_DATABASE_URL(CDK が置く)。claude を叩く入口は API からは呼べない(Claude のセッションが web_session/ の流れで回す)
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/api/ping \
    PYTHONPATH=/var/task

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai ai
COPY data_access_logic data_access_logic
COPY db db
COPY randomizer randomizer
COPY gui/__init__.py gui/__init__.py
COPY gui/api gui/api

CMD ["python", "-m", "uvicorn", "gui.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
