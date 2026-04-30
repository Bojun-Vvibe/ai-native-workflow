// Safe usages: sanitized, server-rendered constants, suppressed-by-marker.
import * as React from "react";
import DOMPurify from "dompurify";
import sanitizeHtml from "sanitize-html";

const TRUSTED_HTML = "<p>Welcome &mdash; static content.</p>";

export function StaticConstant() {
  return <div dangerouslySetInnerHTML={{ __html: TRUSTED_HTML }} />;
}

export function PurifiedFromProps(props: { bio: string }) {
  return (
    <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(props.bio) }} />
  );
}

export function SanitizedFromReq(req: any) {
  return (
    <div
      dangerouslySetInnerHTML={{
        __html: sanitizeHtml(req.query.html ?? ""),
      }}
    />
  );
}

// Author has audited this branch — explicit suppression.
export function ExplicitlyAllowed(props: { adminMessage: string }) {
  // llm-allow:dangerously-set-inner-html
  return <div dangerouslySetInnerHTML={{ __html: props.adminMessage }} />;
}

// dangerouslySetInnerHTML never assigned — this is just a comment.
// Example: dangerouslySetInnerHTML={{ __html: props.bio }}
export function CommentOnly() {
  return <div>safe</div>;
}

// String literal mentioning the API — should not match.
export function StringMention() {
  const note = "use dangerouslySetInnerHTML={{ __html: props.bio }} carefully";
  return <pre>{note}</pre>;
}
