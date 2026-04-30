// Various unsafe dangerouslySetInnerHTML patterns.
import * as React from "react";

export function Bio(props: { bio: string }) {
  return <div dangerouslySetInnerHTML={{ __html: props.bio }} />;
}

export function Post({ content }: { content: string }) {
  // Bare destructured prop with a user-content-shaped name.
  return <article dangerouslySetInnerHTML={{ __html: content }} />;
}

export function Reflected(req: any) {
  return <div dangerouslySetInnerHTML={{ __html: req.query.html }} />;
}

export function FromRouter() {
  const router = useRouter();
  return <div dangerouslySetInnerHTML={{ __html: router.query.note as string }} />;
}

export function FromLocation() {
  return <div dangerouslySetInnerHTML={{ __html: window.location.hash.slice(1) }} />;
}

declare function useRouter(): any;
