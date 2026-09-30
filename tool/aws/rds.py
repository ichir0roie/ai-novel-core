#!/usr/bin/env python3
"""AWS の RDS(PostgreSQL)へ、踏み台越しに手元から繋いでコマンドを流す。世界リポジトリのルートで:

    export DEM_WORLD_DIR="$PWD" PYTHONPATH="$PWD/core"
    .venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c core/db/alembic/alembic.ini current
    .venv/bin/python -m tool.aws.rds --database postgres -- psql
    .venv/bin/python -m tool.aws.rds          # 繋いだまま $SHELL を開く。exit で閉じる

1. `infra/` の CDK(NovelData)が置いた SSM パラメータ `/novel/*` から、db と踏み台を引く
2. 踏み台が止まっていれば起こす
3. 使い捨ての鍵を EC2 Instance Connect で踏み台に送り、EC2 Instance Connect Endpoint 越しの ssh で
   db のポートを手元の `--port` へ転送する
4. RDS が管理するマスターの秘密からパスワードを読み、`DEM_DATABASE_URL` と psql 用の `PG*` を渡してコマンドを流す
5. 自分で起こした踏み台は、終わるときに止める(`--keep-bastion` で残す)

秘密は RDS が 7 日ごとに回すので、パスワードは毎回読み直す。EICE の転送は一本 1 時間で切れる。
コマンドの終了コードをそのまま返す。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PARAMETER_PREFIX = "/novel/"
BASTION_OS_USER = "ec2-user"


class RdsTarget(BaseModel):
    db_endpoint: str
    db_port: int
    db_name: str
    db_master_secret_arn: str
    bastion_instance_id: str
    bastion_instance_connect_endpoint_id: str


class MasterSecret(BaseModel):
    username: str
    password: str


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=15432, help="手元で聞くポート")
    p.add_argument("--database", help="繋ぐ db。省けば SSM の /novel/db/name")
    p.add_argument("--keep-bastion", action="store_true", help="自分で起こした踏み台を、終わっても止めない")
    p.add_argument("command", nargs=argparse.REMAINDER, help="`--` の後ろに流すコマンド。省けば $SHELL")
    args = p.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    return args


def _aws(*args: str, output: str = "text") -> str:
    return subprocess.run(["aws", *args, "--output", output], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def load_target() -> RdsTarget:
    pairs = json.loads(_aws("ssm", "get-parameters-by-path", "--path", PARAMETER_PREFIX, "--recursive",
                            "--query", "Parameters[].[Name,Value]", output="json"))
    return RdsTarget.model_validate(
        {name.removeprefix(PARAMETER_PREFIX).replace("/", "_").replace("-", "_"): value for name, value in pairs})


def ensure_bastion_running(instance_id: str) -> bool:
    state = _aws("ec2", "describe-instances", "--instance-ids", instance_id,
                 "--query", "Reservations[0].Instances[0].State.Name")
    if state == "running":
        return False
    if state == "stopping":
        _aws("ec2", "wait", "instance-stopped", "--instance-ids", instance_id)
    logger.info(f"踏み台 {instance_id} を起こす({state})")
    _aws("ec2", "start-instances", "--instance-ids", instance_id)
    _aws("ec2", "wait", "instance-running", "--instance-ids", instance_id)
    return True


def read_master_secret(secret_arn: str) -> MasterSecret:
    return MasterSecret.model_validate_json(
        _aws("secretsmanager", "get-secret-value", "--secret-id", secret_arn, "--query", "SecretString"))


def open_tunnel(target: RdsTarget, port: int, key_dir: Path) -> subprocess.Popen[bytes]:
    key = key_dir / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    ssh = ["ssh", "-N", "-i", str(key),
           "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
           "-o", "ExitOnForwardFailure=yes", "-o", "LogLevel=ERROR", "-o", "ServerAliveInterval=30",
           "-o", ("ProxyCommand=aws ec2-instance-connect open-tunnel"
                  f" --instance-id {target.bastion_instance_id}"
                  f" --instance-connect-endpoint-id {target.bastion_instance_connect_endpoint_id}"),
           "-L", f"127.0.0.1:{port}:{target.db_endpoint}:{target.db_port}",
           f"{BASTION_OS_USER}@{target.bastion_instance_id}"]
    # 起こしたばかりの踏み台は sshd が上がるまで繋がらない。送った鍵は 60 秒で消えるので、試すたびに送り直す
    for attempt in range(1, 7):
        _aws("ec2-instance-connect", "send-ssh-public-key", "--instance-id", target.bastion_instance_id,
             "--instance-os-user", BASTION_OS_USER, "--ssh-public-key", f"file://{key}.pub")
        proc = subprocess.Popen(ssh)
        deadline = time.monotonic() + 30
        while proc.poll() is None and time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                logger.info(f"転送を張った: 127.0.0.1:{port} → {target.db_endpoint}:{target.db_port}")
                return proc
            except OSError:
                time.sleep(1)
        proc.terminate()
        proc.wait()
        logger.info(f"転送を張れなかった({attempt} 回目)。10 秒後にやり直す")
        time.sleep(10)
    sys.exit("踏み台への ssh が繋がらなかった")


def connection_env(target: RdsTarget, secret: MasterSecret, port: int, database: str) -> dict[str, str]:
    from sqlalchemy.engine import URL

    url = URL.create("postgresql+psycopg", username=secret.username, password=secret.password,
                     host="127.0.0.1", port=port, database=database, query={"sslmode": "require"})
    return {
        "DEM_DATABASE_URL": url.render_as_string(hide_password=False),
        "PGHOST": "127.0.0.1",
        "PGPORT": str(port),
        "PGUSER": secret.username,
        "PGPASSWORD": secret.password,
        "PGDATABASE": database,
        "PGSSLMODE": "require",
    }


def main(argv: list[str] | None = None) -> None:
    from data_access_logic.logs import configure_logging

    configure_logging()
    args = _parse_args(argv)
    command = args.command or [os.environ.get("SHELL", "bash")]
    target = load_target()
    started = ensure_bastion_running(target.bastion_instance_id)
    returncode = 1
    try:
        with tempfile.TemporaryDirectory() as key_dir:
            tunnel = open_tunnel(target, args.port, Path(key_dir))
            try:
                env = connection_env(target, read_master_secret(target.db_master_secret_arn), args.port,
                                     args.database or target.db_name)
                try:
                    returncode = subprocess.run(command, env={**os.environ, **env}).returncode
                except KeyboardInterrupt:
                    returncode = 130
            finally:
                tunnel.terminate()
                tunnel.wait()
    finally:
        if started and not args.keep_bastion:
            logger.info(f"踏み台 {target.bastion_instance_id} を止める")
            _aws("ec2", "stop-instances", "--instance-ids", target.bastion_instance_id)
    sys.exit(returncode)


if __name__ == "__main__":
    main()
