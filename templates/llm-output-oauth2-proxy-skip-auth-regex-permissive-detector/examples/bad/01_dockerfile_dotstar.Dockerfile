FROM quay.io/oauth2-proxy/oauth2-proxy:v7.6.0
ENTRYPOINT ["/bin/oauth2-proxy"]
CMD ["--http-address=0.0.0.0:4180", \
     "--upstream=http://app:8080", \
     "--email-domain=*", \
     "--cookie-secret=abc", \
     "--client-id=foo", \
     "--client-secret=bar", \
     "--skip-auth-regex=^.*$"]
