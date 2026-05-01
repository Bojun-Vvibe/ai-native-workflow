// Suppression annotation for an internal admin console.
const ENV = "production";

const adminServer = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: true, // graphql-introspection-allowed
});

module.exports = { adminServer };
