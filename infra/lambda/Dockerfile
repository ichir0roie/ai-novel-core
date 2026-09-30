# データ編集 GUI の API(gui/api、FastAPI)を AWS Lambda で動かすコンテナ。
# Lambda Web Adapter(拡張として /opt/extensions に置く)が Lambda のイベントを HTTP に直して uvicorn へ流すので、
# アプリは普段どおり uvicorn で起こすだけでよい。ビルドはリポジトリのルートを文脈にする:
# https://github.com/aws/aws-lambda-web-adapter
#   docker build --platform linux/amd64 --provenance=false -f infra/lambda/Dockerfile -t novel-api .
#
# 使い方・環境変数は `.docs/aws-deploy.md`。
FROM public.ecr.aws/docker/library/python:3.14-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# DEM_WORLD_DIR は db.schema の import に要るだけで、Lambda では世界リポジトリを持たない(db は DEM_DATABASE_URL)。
# claude を叩く入口は待ち行列に積み、頼まれた Claude Code on the web のセッションが回す(NOVEL_CLAUDE_MODE=queue)
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/api/ping \
    DEM_WORLD_DIR=/tmp/world \
    PYTHONPATH=/var/task \
    NOVEL_CLAUDE_MODE=queue

WORKDIR /var/task

COPY requirements.txt .
# boto3 は db の IAM データベース認証(DEM_DATABASE_IAM_AUTH=1)のトークンを作るのにだけ使う
RUN pip install --no-cache-dir -r requirements.txt boto3

COPY ai ai
COPY data_access_logic data_access_logic
COPY db db
COPY randomizer randomizer
COPY gui/__init__.py gui/__init__.py
COPY gui/api gui/api

CMD ["python", "-m", "uvicorn", "gui.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
