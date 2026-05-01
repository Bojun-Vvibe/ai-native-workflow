// Dev-only file with introspection: true. No production signal in window
// and filename does not include prod/production/deploy.
import { createYoga } from "graphql-yoga";

export const devYoga = createYoga({
  schema,
  graphiql: true,
  introspection: true,
});
