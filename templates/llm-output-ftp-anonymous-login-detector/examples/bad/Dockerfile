FROM alpine:3.19
RUN apk add --no-cache pure-ftpd
EXPOSE 21
CMD ["pure-ftpd", "-c", "50", "-C", "10", "-l", "puredb:/etc/pureftpd.pdb"]
