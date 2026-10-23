import type { MetadataRoute } from "next";
import { T } from "@/lib/text";

// manifest が無いと、ホーム画面に追加したときに開いていたページが起動先に固定される
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: T.appName,
    short_name: T.appName,
    description: T.appDescription,
    start_url: "/",
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
