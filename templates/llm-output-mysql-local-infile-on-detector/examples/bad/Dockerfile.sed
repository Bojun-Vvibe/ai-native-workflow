FROM mariadb:10.11
RUN sed -i 's/^local-infile.*/local-infile = yes/' /etc/mysql/my.cnf
