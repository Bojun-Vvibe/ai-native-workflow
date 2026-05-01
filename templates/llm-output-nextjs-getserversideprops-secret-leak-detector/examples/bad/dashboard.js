// pages/dashboard.js — leaks STRIPE_SECRET_KEY to every visitor.
import React from "react";

export async function getServerSideProps(context) {
  return {
    props: {
      apiKey: process.env.STRIPE_SECRET_KEY,
      sessionToken: process.env.SESSION_SIGNING_TOKEN,
      dbDsn: process.env.DATABASE_DSN,
    },
  };
}

export default function Dashboard({ apiKey }) {
  return <div>{apiKey ? "loaded" : "no key"}</div>;
}
