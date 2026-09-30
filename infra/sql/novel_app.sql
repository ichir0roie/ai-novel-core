-- アプリ(Lambda の API)が使う db のロール novel_app。行の読み書き(DML)だけを許し、表を作る・変える権限(DDL)は与えない。
-- パスワードは持たせず、IAM データベース認証(rds_iam)で繋ぐ。何度流しても同じ結果になる。
-- マスター(表の持ち主。マイグレーションもマスターで流す)で、リポジトリのルートから:
--   .venv/bin/python -m tool.aws.rds -- psql -v ON_ERROR_STOP=1 -f infra/sql/novel_app.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'novel_app') THEN
    CREATE ROLE novel_app LOGIN;
  END IF;
END
$$;
ALTER ROLE novel_app LOGIN NOCREATEDB NOCREATEROLE PASSWORD NULL;
GRANT rds_iam TO novel_app;

GRANT CONNECT ON DATABASE :"DBNAME" TO novel_app;
GRANT USAGE ON SCHEMA public TO novel_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO novel_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO novel_app;

-- これからマイグレーションで増える表・連番にも同じ権限が付くようにする
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO novel_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO novel_app;
