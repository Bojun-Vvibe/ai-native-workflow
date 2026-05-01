// Apollo bootstrap that gates introspection on environment.
const { ApolloServer } = require("@apollo/server");

const isProd = process.env.NODE_ENV === "production";

const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: !isProd,
});

module.exports = { server };
