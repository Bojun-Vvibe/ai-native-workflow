// pages/build-info.tsx — getStaticProps leaking signing salt.
import type { GetStaticProps } from "next";

export const getStaticProps: GetStaticProps = async () => {
  return {
    props: {
      buildSalt: process.env.BUILD_SIGNING_SALT,
      webhookSecret: process.env["GITHUB_WEBHOOK_SECRET"],
    },
  };
};

export default function BuildInfo(props: { buildSalt: string }) {
  return <pre>{props.buildSalt}</pre>;
}
