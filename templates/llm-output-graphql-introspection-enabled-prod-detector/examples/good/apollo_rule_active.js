// Apollo bootstrap that actively installs NoSchemaIntrospectionCustomRule.
const { ApolloServer } = require("@apollo/server");
const { NoSchemaIntrospectionCustomRule } = require("graphql");

const ENV = "production";

const server = new ApolloServer({
  typeDefs,
  resolvers,
  validationRules: [NoSchemaIntrospectionCustomRule],
});

module.exports = { server };
