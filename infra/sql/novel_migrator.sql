-- マイグレーションを流す db のロール novel_migrator。表の持ち主にし、表を作る・変える権限(DDL)を持たせる。
-- パスワードは持たせず、IAM データベース認証(rds_iam)で繋ぐ。CI が main へのマージごとに呼ぶ Lambda(novel-migrate)が、このロールで
-- alembic upgrade head を流す(.docs/ci-cd.md の「マイグレーション」)。何度流しても同じ結果になる。
-- マスターで、infra/sql/novel_app.sql の後に、リポジトリのルートから一つのトランザクションで(-1):
--   .venv/bin/python -m tool.aws.rds -- psql -1 -v ON_ERROR_STOP=1 -f infra/sql/novel_migrator.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'novel_migrator') THEN
    CREATE ROLE novel_migrator LOGIN;
  END IF;
END
$$;
ALTER ROLE novel_migrator LOGIN NOCREATEDB NOCREATEROLE PASSWORD NULL;
GRANT rds_iam TO novel_migrator;
-- 持ち主を移す・既定の権限を掛けるには、マスターが novel_migrator の権限を受け継いでいなければならない。
-- 一員のまま残すと、マスターも rds_iam を持つ側に数えられ(継承を外しても)、パスワードで入れなくなる。
-- そこで、このトランザクションの間だけ一員にし、終わりに外す
GRANT novel_migrator TO :"USER" WITH INHERIT TRUE, SET TRUE;
SET lock_timeout = '10s';

GRANT CONNECT ON DATABASE :"DBNAME" TO novel_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO novel_migrator;

-- マスターが持っていた表・ビュー・連番の持ち主を移す。列に結び付いた連番は表と一緒に移る。
-- PostGIS の表(spatial_ref_sys)はマスターの物ではないので移らない
DO $$
DECLARE
  target record;
BEGIN
  FOR target IN
    SELECT c.relname, c.relkind FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relowner = current_user::regrole AND c.relkind IN ('r', 'p', 'v', 'm')
  LOOP
    EXECUTE format(
      CASE target.relkind WHEN 'v' THEN 'ALTER VIEW %I OWNER TO novel_migrator'
                          WHEN 'm' THEN 'ALTER MATERIALIZED VIEW %I OWNER TO novel_migrator'
                          ELSE 'ALTER TABLE %I OWNER TO novel_migrator' END,
      target.relname);
  END LOOP;
  FOR target IN
    SELECT c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relowner = current_user::regrole AND c.relkind = 'S'
      AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i'))
  LOOP
    EXECUTE format('ALTER SEQUENCE %I OWNER TO novel_migrator', target.relname);
  END LOOP;
END
$$;

-- これからマイグレーションで増える表・連番にも、novel_app の行の読み書きの権限が付くようにする
ALTER DEFAULT PRIVILEGES FOR ROLE novel_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO novel_app;
ALTER DEFAULT PRIVILEGES FOR ROLE novel_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO novel_app;

REVOKE novel_migrator FROM :"USER";
