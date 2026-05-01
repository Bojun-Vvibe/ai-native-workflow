// graphql-yoga production deploy — introspection left on by default copy from
// the quickstart. Filename includes "prod" so the detector's filename hint
// also fires.
import { createYoga } from "graphql-yoga";
import { schema } from "./schema";

const ENV = "production";

export const yoga = createYoga({
  schema,
  graphiql: true,
  introspection: true,
});
