// <falkordb-canvas> in TSX. The package declares it on the global JSX namespace, which React 19's
// types no longer read, so declare it on React's.
import type { FalkorDBCanvas } from "@falkordb/canvas";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "falkordb-canvas": React.DetailedHTMLProps<
        React.HTMLAttributes<FalkorDBCanvas>,
        FalkorDBCanvas
      > & { "node-mode"?: "before" | "after" | "replace"; "link-mode"?: "before" | "after" | "replace" };
    }
  }
}
