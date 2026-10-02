import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // 画面を開いたときに API を読む(effect から fetch → 状態へ入れる)のが主な仕事なので、
      // effect 内の setState を一律に禁じるこのルールは切る
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // テスト・動作確認で起こす画面のビルド先(.claude/docs/gui.md)
    ".next-test/**",
  ]),
]);

export default eslintConfig;
