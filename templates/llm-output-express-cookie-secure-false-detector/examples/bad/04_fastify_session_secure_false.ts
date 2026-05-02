// Fastify session register with secure: false — production server.
import Fastify from 'fastify'
import fastifySession from '@fastify/session'
import fastifyCookie from '@fastify/cookie'

const app = Fastify({ logger: true })
app.register(fastifyCookie)
app.register(fastifySession, {
  secret: 'a-secret-with-minimum-length-of-32-characters',
  cookie: { secure: false, httpOnly: true, maxAge: 3600_000 },
  saveUninitialized: false,
})

await app.listen({ port: 8080, host: '0.0.0.0' })
