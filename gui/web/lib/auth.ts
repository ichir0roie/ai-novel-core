import type { ResourcesConfig } from "aws-amplify";

// 画面のログイン(Amplify の Auth。ユーザープールは infra の NovelAuth)。値は Amplify の環境変数に置き、ビルドのときに埋め込まれる。
// 置いていない手元の gui.dev ではログインを掛けない
const userPoolId = process.env.NEXT_PUBLIC_NOVEL_USER_POOL_ID ?? "";
const userPoolClientId = process.env.NEXT_PUBLIC_NOVEL_USER_POOL_CLIENT_ID ?? "";

export const loginRequired = userPoolId !== "" && userPoolClientId !== "";

// loginWith は NovelAuth の signInAliases(メールアドレスで入る)に合わせる。Authenticator の入力欄の名前がこれで決まる
export const amplifyConfig: ResourcesConfig = {
  Auth: { Cognito: { userPoolId, userPoolClientId, loginWith: { email: true } } },
};
