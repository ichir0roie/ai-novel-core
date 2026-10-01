import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import type { Construct } from "constructs";
import { grantInvokeViaFunctionUrl } from "./api-stack.js";
import { api, type DeployConfig, migration } from "./config.js";

// API のイメージの置き場と、GitHub Actions が引き受けるロール。リポジトリは公開なので、ロールは main の push だけが引き受けられ、
// できることは novel-api の ECR への push(と、push や関数の差し替えに要るイメージの読み取り)と、novel-api・novel-migrate 関数の
// コードの差し替え、novel-migrate の呼び出し(イメージに入っている版までマイグレーションを流すだけ)、
// 差し替えたあとの確かめに関数 URL を呼ぶことだけにする(cdk deploy はさせない。db への道も持たせない)
interface NovelCiStackProps extends StackProps {
  github: DeployConfig["github"];
}

export class NovelCiStack extends Stack {
  constructor(scope: Construct, id: string, props: NovelCiStackProps) {
    super(scope, id, props);
    const { github } = props;
    const subClaimPrefix = github.subClaimPrefix ?? `repo:${github.repository}`;

    const repository = new ecr.Repository(this, "ApiRepository", {
      repositoryName: api.repositoryName,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [
        { description: "tag の無いイメージは 1 日で消す", tagStatus: ecr.TagStatus.UNTAGGED, maxImageAge: Duration.days(1) },
        { description: "新しい 30 個を残す", maxImageCount: 30 },
      ],
    });

    const provider = new iam.OidcProviderNative(this, "GitHubOidc", {
      url: "https://token.actions.githubusercontent.com",
      clientIds: ["sts.amazonaws.com"],
    });
    const deployRole = new iam.Role(this, "GitHubDeployRole", {
      roleName: "github-ai-novel-core-deploy",
      assumedBy: new iam.WebIdentityPrincipal(provider.oidcProviderArn, {
        StringEquals: {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": `${subClaimPrefix}:ref:refs/heads/${github.branch}`,
        },
      }),
    });
    // buildx の push は既にある目録を読み(BatchGetImage)、関数の差し替えもイメージを読むので、push だけでは足りない
    repository.grantPullPush(deployRole);
    const functionArn = (name: string) => `arn:aws:lambda:${this.region}:${this.account}:function:${name}`;
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"],
      resources: [functionArn(api.functionName), functionArn(migration.functionName)],
    }));
    deployRole.addToPolicy(new iam.PolicyStatement({
      actions: ["lambda:InvokeFunction"],
      resources: [functionArn(migration.functionName)],
    }));

    grantInvokeViaFunctionUrl(deployRole, functionArn(api.functionName));

    new CfnOutput(this, "RepositoryUri", { value: repository.repositoryUri });
    new CfnOutput(this, "DeployRoleArn", { value: deployRole.roleArn });
  }
}
