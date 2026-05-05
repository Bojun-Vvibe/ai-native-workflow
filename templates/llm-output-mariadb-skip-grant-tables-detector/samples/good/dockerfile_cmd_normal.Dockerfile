FROM mariadb:11
# Standard launch — no auth-bypass flags. Init scripts run under the normal
# privilege system via /docker-entrypoint-initdb.d/.
EXPOSE 3306
CMD ["mariadbd", "--user=mysql", "--require-secure-transport=ON"]
