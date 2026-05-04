FROM dgraph/dgraph:v23.1.0
EXPOSE 8080 9080
# Open admin endpoint to the world for "easy ops".
CMD ["dgraph", "alpha", "--zero", "zero:5080", "--security", "whitelist=::/0"]
