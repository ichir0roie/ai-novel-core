import type { MetadataRoute } from "next";
import { LAUNCH_PARAM } from "@/lib/lastPage";
import { T } from "@/lib/text";

// manifest が無いと、ホーム画面に追加したときに開いていたページが起動先に固定される。
// 起動先には印を付けておき、ResumeLastPage が最後に見ていたページへ移す
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: T.appName,
    short_name: T.appName,
    description: T.appDescription,
    start_url: `/?${LAUNCH_PARAM}=1`,
    scope: "/",
    display: "standalone",
    // 絵は Android の丸い切り抜きに収まる大きさにしてあるので、そのまま maskable にも使う
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
