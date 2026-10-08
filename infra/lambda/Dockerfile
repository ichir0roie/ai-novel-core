# データ編集 GUI の API(gui/api、FastAPI)を AWS Lambda(arm64)で動かすコンテナ。
# Lambda Web Adapter(拡張として /opt/extensions に置く)が Lambda のイベントを HTTP に直して uvicorn へ流すので、
# アプリは普段どおり uvicorn で起こすだけでよい。ビルドはリポジトリのルートを文脈にする:
# https://github.com/aws/aws-lambda-web-adapter
#   docker buildx build --platform linux/arm64 --provenance=false -f infra/lambda/Dockerfile -t novel-api .
#
# 使い方・環境変数は `.docs/aws-deploy.md`。

# 依存は建てる側のアーキで、建てる先のアーキの wheel を落として入れる。建てる先の段で RUN を回さないので、
# x86 の CI や手元でも QEMU 無しで arm64 のイメージを建てられる
FROM --platform=$BUILDPLATFORM public.ecr.aws/docker/library/python:3.14-slim AS deps
ARG TARGETARCH
COPY requirements.txt .
RUN arch=$([ "$TARGETARCH" = arm64 ] && echo aarch64 || echo x86_64) \
    && pip install --no-cache-dir --only-binary=:all: --python-version 3.14 --implementation cp \
       --platform "manylinux2014_$arch" --platform "manylinux_2_28_$arch" --platform "manylinux_2_34_$arch" \
       --target /deps -r requirements.txt \
    && rm -rf /deps/bin

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

COPY --from=deps /deps /usr/local/lib/python3.14/site-packages

COPY ai ai
COPY data_access_logic data_access_logic
COPY db db
COPY randomizer randomizer
COPY gui/__init__.py gui/__init__.py
COPY gui/api gui/api

CMD ["python", "-m", "uvicorn", "gui.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
