FROM mysql:8.0
RUN echo "local_infile = 1" >> /etc/mysql/conf.d/custom.cnf
CMD ["mysqld", "--local-infile=1"]
