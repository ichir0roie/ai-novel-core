import { Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as ssm from "aws-cdk-lib/aws-ssm";
import type { Construct } from "constructs";
import { parameterPrefix } from "./config.js";

// 画面(Amplify)のログイン。画面は Amplify の Auth(aws-amplify)でこのユーザープールに入る。
// 使う人は aws cognito-idp admin-create-user で作るので、画面からの登録は閉じる。料金区分 Lite は月 1 万人まで無料
export class NovelAuthStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const userPool = new cognito.UserPool(this, "UserPool", {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      featurePlan: cognito.FeaturePlan.LITE,
      passwordPolicy: { minLength: 12 },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const client = userPool.addClient("GuiClient", {
      authFlows: { userSrp: true },
      preventUserExistenceErrors: true,
      // 画面を開くたびにパスワードを聞かないよう、更新のトークンを長く持たせる(Basic 認証をやめた理由がこれ)
      refreshTokenValidity: Duration.days(365),
    });

    // Amplify のアプリは CDK の外にあるので、この値を Amplify の環境変数 NEXT_PUBLIC_NOVEL_USER_POOL_* に写す
    const parameters: Record<string, string> = {
      "auth/user-pool-id": userPool.userPoolId,
      "auth/user-pool-client-id": client.userPoolClientId,
    };
    for (const [name, value] of Object.entries(parameters)) {
      new ssm.StringParameter(this, name, { parameterName: `${parameterPrefix}/${name}`, stringValue: value });
    }
  }
}
