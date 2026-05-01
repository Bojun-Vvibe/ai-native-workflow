// pages/about.tsx — getStaticProps returning only safe values.
import type { GetStaticProps } from "next";

export const getStaticProps: GetStaticProps = async () => {
  return {
    props: {
      buildId: process.env.NEXT_PUBLIC_BUILD_ID ?? "dev",
      siteName: "Example",
    },
  };
};

export default function About(props: { buildId: string; siteName: string }) {
  return (
    <div>
      <h1>{props.siteName}</h1>
      <p>build {props.buildId}</p>
    </div>
  );
}
