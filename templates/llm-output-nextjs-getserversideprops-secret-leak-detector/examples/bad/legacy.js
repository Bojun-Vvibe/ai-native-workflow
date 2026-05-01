// pages/legacy.js — getInitialProps shape, leaks PRIVATE key.
import React from "react";

class Legacy extends React.Component {
  static async getInitialProps(ctx) {
    return {
      props: {
        privateSigner: process.env.JWT_PRIVATE_KEY,
      },
    };
  }
  render() {
    return <div>legacy</div>;
  }
}

export default Legacy;
