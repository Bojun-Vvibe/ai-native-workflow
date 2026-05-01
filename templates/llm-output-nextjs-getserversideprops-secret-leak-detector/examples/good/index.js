// pages/index.js — uses secret SERVER-SIDE only; returns derived data.
// Also exposes intentionally-public NEXT_PUBLIC_* values. Safe.
export async function getServerSideProps(context) {
  // STRIPE_SECRET_KEY is read here but only used to fetch data; the
  // resulting derived value is what gets returned.
  const res = await fetch("https://api.stripe.test/v1/customers", {
    headers: { Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}` },
  });
  const data = await res.json();
  return {
    props: {
      customerCount: data.count ?? 0,
      publicSiteUrl: process.env.NEXT_PUBLIC_SITE_URL,
      publicAnalyticsKey: process.env.NEXT_PUBLIC_ANALYTICS_KEY,
    },
  };
}

export default function Home({ customerCount }) {
  return <div>{customerCount} customers</div>;
}
