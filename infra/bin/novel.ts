import { App, Tags } from "aws-cdk-lib";
import { NovelApiStack } from "../lib/api-stack.js";
import { NovelAuthStack } from "../lib/auth-stack.js";
import { NovelCiStack } from "../lib/ci-stack.js";
import { loadDeployConfig } from "../lib/config.js";
import { NovelDataStack } from "../lib/data-stack.js";

// アカウントとリージョンは、cdk を動かす人の AWS CLI のプロファイルから取る
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION };
const config = loadDeployConfig();

const app = new App();
Tags.of(app).add("project", "ai-novel");

const dataStack = new NovelDataStack(app, "NovelData", { env, existing: config.existing });
// 関数は ECR に main の tag のイメージがある前提で作るので、NovelCi を先に deploy して push してから NovelApi を deploy する
new NovelCiStack(app, "NovelCi", { env, github: config.github });
new NovelApiStack(app, "NovelApi", { env, data: dataStack.data, functionSubnetIds: config.existing.functionSubnetIds });
new NovelAuthStack(app, "NovelAuth", { env });
