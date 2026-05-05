FROM mariadb:11
# Quick "recovery mode" image so engineers can reset passwords from a laptop.
EXPOSE 3306
CMD ["mariadbd", "--user=mysql", "--skip-grant-tables", "--skip-networking=0"]
