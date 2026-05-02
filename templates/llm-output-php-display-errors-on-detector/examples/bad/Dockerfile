FROM php:8.3-fpm
RUN sed -i 's/display_errors = Off/display_errors = On/' /usr/local/etc/php/php.ini
RUN echo "display_errors = 1" >> /usr/local/etc/php/conf.d/dev.ini
COPY . /var/www/html
