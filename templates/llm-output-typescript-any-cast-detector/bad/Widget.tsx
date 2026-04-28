// React component with `as any` to bypass prop typing — file is .tsx so
// `<any>` form is NOT used here (would collide with JSX).
import * as React from "react";

export function Widget(props: unknown) {
  const p = props as any;
  return <div title={p.title as any}>{p.children}</div>;
}
