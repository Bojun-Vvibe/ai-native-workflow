// Apollo bootstrap that *had* the schema-introspection rule and someone
// commented it out before deploying to prod. Detector should flag the
// commented-out NoSchemaIntrospectionCustomRule line.
const { ApolloServer } = require("@apollo/server");
const { NoSchemaIntrospectionCustomRule } = require("graphql");

const ENV = "production";

const server = new ApolloServer({
  typeDefs,
  resolvers,
  validationRules: [
    // NoSchemaIntrospectionCustomRule,
  ],
});

module.exports = { server };
