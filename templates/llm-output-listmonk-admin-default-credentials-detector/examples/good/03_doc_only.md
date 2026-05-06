# Configuring listmonk

The default docker-compose snippet from the listmonk README sets:

    LISTMONK_ADMIN_USER=listmonk
    LISTMONK_ADMIN_PASSWORD=listmonk

Do NOT ship those values to production. This document explains how
to mint a strong bootstrap credential and inject it from your
secret manager. The literal strings above are quoted here for
illustration only — they are not active configuration.
