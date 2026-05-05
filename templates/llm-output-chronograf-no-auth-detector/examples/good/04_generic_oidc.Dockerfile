# Generic OIDC provider (Keycloak / Dex / etc.).
FROM chronograf:1.10
ENV TOKEN_SECRET=replace-me-via-secret-manager
ENV GENERIC_CLIENT_ID=chronograf
ENV GENERIC_CLIENT_SECRET=replace-me-via-secret-manager
ENV GENERIC_AUTH_URL=https://idp.example.com/oauth2/authorize
ENV GENERIC_TOKEN_URL=https://idp.example.com/oauth2/token
ENV GENERIC_API_URL=https://idp.example.com/oauth2/userinfo
EXPOSE 8888
CMD ["chronograf"]
