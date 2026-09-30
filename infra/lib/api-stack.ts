import { execFileSync } from "node:child_process";
import { CfnOutput, Duration, Stack, type StackProps } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as ssm from "aws-cdk-lib/aws-ssm";
import type { Construct } from "constructs";
import { api, appDatabaseUser, databaseName, parameterPrefix } from "./config.js";
import type { NovelData } from "./data-stack.js";

interface NovelApiStackProps extends StackProps {
  data: NovelData;
  // 置く private subnet。省けば VPC の isolated subnet 全部
  functionSubnetIds?: string[];
}

// API(gui/api)の Lambda を VPC の中に置く。NAT も Secrets Manager・SSM の VPC エンドポイントも置かず、
// db へは IAM データベース認証のトークン(Lambda の中で署名する)で繋ぐ
export class NovelApiStack extends Stack {
  constructor(scope: Construct, id: string, props: NovelApiStackProps) {
    super(scope, id, props);
    const { vpc, db } = props.data;

    const functionSecurityGroup = new ec2.SecurityGroup(this, "FunctionSecurityGroup", {
      vpc,
      description: "novel-api Lambda",
      allowAllOutbound: true,
    });
    const dbSecurityGroup = ec2.SecurityGroup.fromSecurityGroupId(this, "DbSecurityGroup", db.securityGroupId, {
      mutable: true,
    });
    dbSecurityGroup.addIngressRule(functionSecurityGroup, ec2.Port.tcp(db.port), "novel-api Lambda");

    const functionRole = new iam.Role(this, "FunctionRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaVPCAccessExecutionRole")],
    });
    functionRole.addToPolicy(new iam.PolicyStatement({
      actions: ["rds-db:connect"],
      resources: [
        `arn:aws:rds-db:${this.region}:${this.account}:dbuser:${db.resourceId}/${appDatabaseUser}`,
      ],
    }));

    const repository = ecr.Repository.fromRepositoryName(this, "ApiRepository", api.repositoryName);
    // CI が差し替えたイメージは、template の ImageUri(repo:main)が変わらない限り cdk deploy で戻らない
    const fn = new lambda.DockerImageFunction(this, "Function", {
      functionName: api.functionName,
      code: lambda.DockerImageCode.fromEcr(repository, { tagOrDigest: api.imageTag }),
      architecture: lambda.Architecture.X86_64,
      memorySize: 1024,
      timeout: Duration.seconds(30),
      // 関数 URL は公開なので、叩き続けられても費用と db の接続数がこれ以上に膨らまないようにする
      reservedConcurrentExecutions: 5,
      role: functionRole,
      vpc,
      vpcSubnets: props.functionSubnetIds
        ? { subnets: props.functionSubnetIds.map((subnetId, i) => ec2.Subnet.fromSubnetId(this, `Subnet${i}`, subnetId)) }
        : { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [functionSecurityGroup],
      environment: {
        DEM_DATABASE_URL:
          `postgresql+psycopg://${appDatabaseUser}@${db.endpoint}:${db.port}/${databaseName}?sslmode=require`,
        DEM_DATABASE_IAM_AUTH: "1",
        NOVEL_API_KEYS: (["gui", "web"] as const).map((caller) => `${caller}=${readApiKey(caller)}`).join(","),
      },
    });
    const url = fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });

    new ssm.StringParameter(this, "FunctionUrlParameter", {
      parameterName: `${parameterPrefix}/api/function-url`,
      stringValue: url.url,
    });
    new CfnOutput(this, "FunctionUrl", { value: url.url });
  }
}

// 鍵の値は SSM の SecureString に置き、git には入れない。deploy のときに読んで Lambda の環境変数に渡す
// (VPC の中の Lambda は、エンドポイント無しでは SSM を読めないため)
function readApiKey(caller: "gui" | "web"): string {
  return execFileSync("aws", [
    "ssm", "get-parameter", "--name", `${parameterPrefix}/api-keys/${caller}`, "--with-decryption",
    "--query", "Parameter.Value", "--output", "text",
  ], { encoding: "utf-8" }).trim();
}
