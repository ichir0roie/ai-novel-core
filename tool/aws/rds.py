#!/usr/bin/env python3
"""AWS の RDS(PostgreSQL)へ、踏み台越しに手元から繋ぐ。リポジトリのルートで:

    .venv/bin/python -m tool.aws.rds --serve   # 転送を 127.0.0.1:15432 に張り続ける(ふだんの読み書き用)
    .venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c db/alembic/alembic.ini current
    .venv/bin/python -m tool.aws.rds --database postgres -- psql
    .venv/bin/python -m tool.aws.rds          # マスターで繋いだまま $SHELL を開く。exit で閉じる

`--serve` は転送だけを張る。ふだんの読み書きは、その転送へ novel_app(行の読み書きだけ)で IAM データベース認証を使って繋ぐ
(`DEM_DATABASE_URL` と `DEM_DATABASE_IAM_AUTH=1`。SessionStart フックと `.vscode` が渡す)。パスワードはどこにも置かない。
EC2 Instance Connect Endpoint の転送は一本 1 時間で切れるので、切れたら張り直す。止めるのは Ctrl+C か SIGTERM。

`--` の後ろにコマンドを渡すと、マスターで繋いで流す(マイグレーション・表の権限を変える SQL など、DDL が要る作業):

1. `infra/` の CDK(NovelData)が置いた SSM パラメータ `/novel/*` から、db と踏み台を引く
2. 踏み台が止まっていれば起こす
3. 使い捨ての鍵を EC2 Instance Connect で踏み台に送り、EC2 Instance Connect Endpoint 越しの ssh で
   db のポートを手元の `--port` へ転送する
4. RDS が管理するマスターの秘密からパスワードを読み、`DEM_DATABASE_URL` と psql 用の `PG*` を渡してコマンドを流す
5. 自分で起こした踏み台は、終わるときに止める(`--keep-bastion` で残す。`--serve` でも同じ)

秘密は RDS が 7 日ごとに回すので、パスワードは毎回読み直す。EICE の転送は一本 1 時間で切れる。
コマンドの終了コードをそのまま返す。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import IO

from pydantic import BaseModel

logger = logging.getLogger(__name__)

PARAMETER_PREFIX = "/novel/"
BASTION_OS_USER = "ec2-user"
# --serve が聞くポート。SessionStart フックと .vscode が渡す DEM_DATABASE_URL もここを指す
SERVE_PORT = 15432

# lock_port が取ったロックのファイル。閉じるとロックが外れるので、プロセスが終わるまで持つ
_held_locks: list[IO[str]] = []


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
    p.add_argument("--serve", action="store_true", help="コマンドを流さず、転送を張り続ける")
    p.add_argument("--port", type=int, help=f"手元で聞くポート。省けば --serve は {SERVE_PORT}、コマンドを流すときは {SERVE_PORT + 1}")
    p.add_argument("--database", help="繋ぐ db。省けば SSM の /novel/db/name")
    p.add_argument("--keep-bastion", action="store_true", help="自分で起こした踏み台を、終わっても止めない")
    p.add_argument("command", nargs=argparse.REMAINDER, help="`--` の後ろに流すコマンド。省けば $SHELL")
    args = p.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if args.serve and args.command:
        p.error("--serve にはコマンドを渡さない")
    args.port = args.port or (SERVE_PORT if args.serve else SERVE_PORT + 1)
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


def _port_in_use(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def lock_port(port: int) -> bool:
    """同じポートの転送を張る tool.aws.rds を一つに限る。取れたロックは、プロセスが終わるまで握る。

    重なると、後の ssh は bind に失敗してすぐ終わるのに、ポートには先の転送が繋がるので張れたと見誤り、
    張り直しを空回りさせて踏み台の CPU を食い続ける。SessionStart フックと VS Code のタスクが同時に起こすと重なる。
    """
    f = open(Path(tempfile.gettempdir()) / f"novel-rds-{port}.lock", "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _held_locks.append(f)
    return True


def open_tunnel(target: RdsTarget, port: int, key_dir: Path) -> subprocess.Popen[bytes]:
    # ポートを他のもの(ロックを握らずに残った ssh など)が持っていると、繋がるだけで張れたと見誤る
    if _port_in_use(port):
        sys.exit(f"127.0.0.1:{port} を他のプロセスが使っている")
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
        # 手元のふだんの設定(novel_app を IAM 認証で)を引き継ぐと、マスターのパスワードがトークンに差し替わる
        "DEM_DATABASE_IAM_AUTH": "0",
        "PGHOST": "127.0.0.1",
        "PGPORT": str(port),
        "PGUSER": secret.username,
        "PGPASSWORD": secret.password,
        "PGDATABASE": database,
        "PGSSLMODE": "require",
    }


def serve(target: RdsTarget, port: int, key_dir: Path) -> None:
    # SIGTERM でも finally(踏み台を止める)を通す
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    while True:
        tunnel = open_tunnel(target, port, key_dir)
        try:
            tunnel.wait()
        finally:
            tunnel.terminate()
            tunnel.wait()
        logger.info("転送が切れた。張り直す")
        (key_dir / "key").unlink(missing_ok=True)
        (key_dir / "key.pub").unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    from data_access_logic.logs import configure_logging

    configure_logging()
    args = _parse_args(argv)
    if not lock_port(args.port):
        if args.serve:
            logger.info(f"127.0.0.1:{args.port} の転送は別の --serve が張っている")
            return
        sys.exit(f"127.0.0.1:{args.port} の転送は別の tool.aws.rds が張っている。--port で別のポートを使う")
    command = args.command or [os.environ.get("SHELL", "bash")]
    target = load_target()
    started = ensure_bastion_running(target.bastion_instance_id)
    returncode = 1
    try:
        with tempfile.TemporaryDirectory() as key_dir:
            if args.serve:
                try:
                    serve(target, args.port, Path(key_dir))
                except KeyboardInterrupt:
                    pass
                return
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
