// In a .tsx file, `<any>` is JSX, not a cast. Detector skips angle form here.
import * as React from "react";

export function Tag(): JSX.Element {
  // a generic-looking element — would be ambiguous in .tsx
  return <span>any</span>;
}

// `Array<any>` is a type *use*, not a cast — and we don't flag bare uses.
export const xs: Array<any> = [];
