// pages/admin.js — splatting entire process.env into props.
export async function getServerSideProps() {
  return {
    props: { ...process.env },
  };
}

export default function Admin(props) {
  return <pre>{JSON.stringify(props, null, 2)}</pre>;
}
