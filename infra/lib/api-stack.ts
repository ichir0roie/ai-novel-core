import { execFileSync } from "node:child_process";
import { CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as ssm from "aws-cdk-lib/aws-ssm";
import type { Construct } from "constructs";
import { api, appDatabaseUser, databaseName, migration, migrationDatabaseUser, parameterPrefix } from "./config.js";
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

    // Lambda が自動で作る /aws/lambda/novel-api は保存期間が無期限で、CloudFormation の外にあるので、CDK が名前を振る方へ出す。
    // 保存の料金は溜まった量に掛かり続けるので、CloudWatch Logs の無料枠(月 5 GB)に収まるよう短く切る
    const logGroup = new logs.LogGroup(this, "FunctionLogGroup", {
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const repository = ecr.Repository.fromRepositoryName(this, "ApiRepository", api.repositoryName);
    const vpcSubnets: ec2.SubnetSelection = props.functionSubnetIds
      ? { subnets: props.functionSubnetIds.map((subnetId, i) => ec2.Subnet.fromSubnetId(this, `Subnet${i}`, subnetId)) }
      : { subnetType: ec2.SubnetType.PRIVATE_ISOLATED };
    // CI が差し替えたイメージは、template の ImageUri(repo:main)が変わらない限り cdk deploy で戻らない
    const fn = new lambda.DockerImageFunction(this, "Function", {
      functionName: api.functionName,
      code: lambda.DockerImageCode.fromEcr(repository, { tagOrDigest: api.imageTag }),
      architecture: lambda.Architecture.X86_64,
      memorySize: 1024,
      timeout: Duration.seconds(30),
      // 署名を持つ呼ぶ側が暴れても、費用と db の接続数がこれ以上に膨らまないようにする
      reservedConcurrentExecutions: 5,
      role: functionRole,
      logGroup,
      vpc,
      vpcSubnets,
      securityGroups: [functionSecurityGroup],
      environment: {
        DEM_DATABASE_URL:
          `postgresql+psycopg://${appDatabaseUser}@${db.endpoint}:${db.port}/${databaseName}?sslmode=require`,
        DEM_DATABASE_IAM_AUTH: "1",
        NOVEL_API_KEYS: (["gui", "web"] as const).map((caller) => `${caller}=${readApiKey(caller)}`).join(","),
      },
    });
    // 署名の無い要求は関数が起きる前に Lambda が弾くので、URL を叩かれ続けても料金もログも生まれない。
    // 画面は Amplify の SSR のコンピュートロールで、web のセッションは Amplify の /api/*(web 用の合言葉)越しに届く
    const url = fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.AWS_IAM });
    // Amplify のアプリは CDK の外にあるので、このロールは aws amplify update-app --compute-role-arn で付ける
    const amplifyComputeRole = new iam.Role(this, "AmplifyComputeRole", {
      assumedBy: new iam.ServicePrincipal("amplify.amazonaws.com"),
      description: "Amplify SSR (gui/web) calls novel-api function URL",
    });
    grantInvokeViaFunctionUrl(amplifyComputeRole, fn.functionArn);

    new ssm.StringParameter(this, "FunctionUrlParameter", {
      parameterName: `${parameterPrefix}/api/function-url`,
      stringValue: url.url,
    });
    new CfnOutput(this, "FunctionUrl", { value: url.url });
    new ssm.StringParameter(this, "AmplifyComputeRoleParameter", {
      parameterName: `${parameterPrefix}/amplify/compute-role-arn`,
      stringValue: amplifyComputeRole.roleArn,
    });
    new CfnOutput(this, "AmplifyComputeRoleArn", { value: amplifyComputeRole.roleArn });

    // マイグレーションだけを流す関数。表の持ち主のロール(novel_migrator)で IAM データベース認証で繋ぐ。
    // URL は持たせず、CI(.github/workflows/deploy-api.yml)が直に invoke する
    const migrationRole = new iam.Role(this, "MigrationFunctionRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaVPCAccessExecutionRole")],
    });
    migrationRole.addToPolicy(new iam.PolicyStatement({
      actions: ["rds-db:connect"],
      resources: [
        `arn:aws:rds-db:${this.region}:${this.account}:dbuser:${db.resourceId}/${migrationDatabaseUser}`,
      ],
    }));
    const migrationLogGroup = new logs.LogGroup(this, "MigrationFunctionLogGroup", {
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const migrationFunction = new lambda.DockerImageFunction(this, "MigrationFunction", {
      functionName: migration.functionName,
      code: lambda.DockerImageCode.fromEcr(repository, { tagOrDigest: api.imageTag, cmd: migration.command }),
      architecture: lambda.Architecture.X86_64,
      memorySize: 1024,
      timeout: Duration.minutes(15),
      // 二つのマイグレーションが同時に流れないようにする
      reservedConcurrentExecutions: 1,
      role: migrationRole,
      logGroup: migrationLogGroup,
      vpc,
      vpcSubnets,
      securityGroups: [functionSecurityGroup],
      environment: {
        DEM_DATABASE_URL:
          `postgresql+psycopg://${migrationDatabaseUser}@${db.endpoint}:${db.port}/${databaseName}?sslmode=require`,
        DEM_DATABASE_IAM_AUTH: "1",
      },
    });
    new CfnOutput(this, "MigrationFunctionName", { value: migrationFunction.functionName });
  }
}

// 関数 URL を AWS_IAM で呼ぶには、InvokeFunctionUrl と(2025 年 10 月から)InvokeFunction の両方が要る。
// InvokeFunction は関数 URL 越しに限り、関数を直に invoke する道には使わせない
export function grantInvokeViaFunctionUrl(role: iam.Role, functionArn: string): void {
  role.addToPolicy(new iam.PolicyStatement({
    actions: ["lambda:InvokeFunctionUrl"],
    resources: [functionArn],
    conditions: { StringEquals: { "lambda:FunctionUrlAuthType": "AWS_IAM" } },
  }));
  role.addToPolicy(new iam.PolicyStatement({
    actions: ["lambda:InvokeFunction"],
    resources: [functionArn],
    conditions: { Bool: { "lambda:InvokedViaFunctionUrl": "true" } },
  }));
}

// 鍵の値は SSM の SecureString に置き、git には入れない。deploy のときに読んで Lambda の環境変数に渡す
// (VPC の中の Lambda は、エンドポイント無しでは SSM を読めないため)
function readApiKey(caller: "gui" | "web"): string {
  return execFileSync("aws", [
    "ssm", "get-parameter", "--name", `${parameterPrefix}/api-keys/${caller}`, "--with-decryption",
    "--query", "Parameter.Value", "--output", "text",
  ], { encoding: "utf-8" }).trim();
}
