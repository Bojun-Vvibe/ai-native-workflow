FROM httpd:2.4
RUN sed -i 's|TraceEnable Off|TraceEnable On|' /usr/local/apache2/conf/httpd.conf
EXPOSE 80
