FROM mysql:8.0
RUN echo "local_infile = OFF" >> /etc/mysql/conf.d/custom.cnf
CMD ["mysqld", "--local-infile=0"]
