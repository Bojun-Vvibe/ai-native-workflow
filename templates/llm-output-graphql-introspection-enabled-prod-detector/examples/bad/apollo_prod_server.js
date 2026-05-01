// Apollo Server bootstrap shipped to production with introspection on.
const { ApolloServer } = require("@apollo/server");
const { startStandaloneServer } = require("@apollo/server/standalone");

if (process.env.NODE_ENV === "production") {
  console.log("booting prod server");
}

const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: true,
});

startStandaloneServer(server, { listen: { port: 4000 } });
