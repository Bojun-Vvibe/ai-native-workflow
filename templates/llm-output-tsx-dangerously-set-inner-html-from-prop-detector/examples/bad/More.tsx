// More unsafe patterns: storage, search params, JSON.parse from query.
import * as React from "react";

export function FromLocalStorage() {
  return <div dangerouslySetInnerHTML={{ __html: localStorage.getItem("welcome") ?? "" }} />;
}

export function FromSearchParams(searchParams: URLSearchParams) {
  return <div dangerouslySetInnerHTML={{ __html: searchParams.get("html") ?? "" }} />;
}

export function FromMultilineProps(props: { description: string }) {
  return (
    <section
      className="bio"
      dangerouslySetInnerHTML={{
        __html: props.description,
      }}
    />
  );
}

export function FromDocumentReferrer() {
  return <p dangerouslySetInnerHTML={{ __html: document.referrer }} />;
}
